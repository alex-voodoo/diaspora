#!./venv/bin/python

"""
See README.md for details
"""
import copy
import gettext
import html
import json
import logging
import re
import sqlite3
import time
import traceback
from collections import deque
from sqlite3 import Connection

import httpx
from langdetect import detect
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, User, ChatMemberLeft, ChatMemberBanned, \
    ChatMember
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters,
                          CallbackQueryHandler, )

from features import antispam

# ----------------------------------------------------------------------------------------------------------------------
# Bot default configuration.
#
# To override these settings, edit `secret.py`.  It is loaded in the bottom and overwrites default values.

# ----------------------------------------------------------------------------------------------------------------------
# Internationalisation
#
# The official documentation suggests that bots should switch to the user's language or fall back to English.  This is
# not completely adequate for this bot that is designed for groups of nationals; the default English may be not optimal.
# The settings below define the "standard" behaviour suggested by the documentation, but may be overridden in secret.py.
#
# Whether the bot should try to switch to the user's language
SPEAK_USER_LANGUAGE = True
# Language to fall back to if there is no translation to the user's language
DEFAULT_LANGUAGE = "en"
# Supported languages.  Must be a subset of languages that present in the `locales` directory.
SUPPORTED_LANGUAGES = ("en", "ru")

# ----------------------------------------------------------------------------------------------------------------------
# Bot personality
#
# Bot name may imply its "gender" that affects "personal" messages (like "I am the host" vs. "I am the hostess").  This
# setting tells which one to pick.
BOT_IS_MALE = False

# ----------------------------------------------------------------------------------------------------------------------
# Greeting new users
#
# The bot can reply to each service message about a new user joining the group.  These bot replies can be deleted by the
# bot after the specified delay.
#
# Whether to greet users that join the group
GREETING_ENABLED = True
# Delay in seconds for deleting the greeting, 0 for not deleting the greetings
GREETING_TIMEOUT = 300

# ----------------------------------------------------------------------------------------------------------------------
# Moderation
#
# The bot may ask the moderators to approve changes made by users to their data records.
#
# Whether moderation is enabled
MODERATION_ENABLED = True
# Whether moderation is "lazy" (True) or "mandatory" (False)
MODERATION_IS_LAZY = True
# Telegram IDs of moderators
MODERATOR_IDS = tuple()

# ----------------------------------------------------------------------------------------------------------------------
# Language moderation
#
# The bot may ask people in the main chat to speak the default language.  If the bot detects too many messages written
# in languages other than the default one, it posts a message that reminds the people about rules of the group.
#
# Whether bot controls languages
LANGUAGE_MODERATION_ENABLED = False
#
# Maximum number of languages in non-default language
LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT = 3
#
# Minimum number of words in a message that the bot should evaluate when detecting the language
LANGUAGE_MODERATION_MIN_WORD_COUNT = 3

# ----------------------------------------------------------------------------------------------------------------------
# Antispam
#
# The bot may detect and delete spam messages.  Spammers in Telegram are normally regular users that join the group, sit
# silent for some time, and then send their junk, hoping that someone will see and buy it before the moderators react.
# Telegram blocks user accounts that have been reported as spammers, which makes it not worth it trying to mimic the
# good user before sending spam.  Therefore, to eliminate most spam, it should be enough to evaluate the first message a
# new user sends to the group.
#
# Whether the feature is enabled
ANTISPAM_ENABLED = False
# Whether to use simple filter that triggers on a single word
ANTISPAM_STOP_WORDS_ENABLED = False
# Whether to use OpenAI-backed filter
ANTISPAM_OPENAI_ENABLED = False
# Whether to use OpenAI-backed filter
ANTISPAM_OPENAI_API_KEY = ""

# ----------------------------------------------------------------------------------------------------------------------
# General settings
#
# Generic delay in seconds for self-destructing messages
DELETE_MESSAGE_TIMEOUT = 60

# Defines some essential configuration parameters, and may re-define settings explained above
from secret import *

# Configure logging
# Set higher logging level for httpx to avoid all GET and POST requests being logged.
logging.basicConfig(format="[%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d] %(message)s", level=logging.INFO, filename="bot.log")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Commands, sequences, and responses
COMMAND_START, COMMAND_HELP, COMMAND_WHO, COMMAND_ENROLL, COMMAND_RETIRE = ("start", "help", "who", "enroll", "retire")
TYPING_OCCUPATION, TYPING_LOCATION, CONFIRMING_LEGALITY = range(3)
RESPONSE_YES, RESPONSE_NO = ("yes", "no")
MODERATOR_APPROVE, MODERATOR_DECLINE = ("approve", "decline")

# Global translation context.  Updated by update_language() depending on the locale of the current user.
_ = gettext.gettext

db_connection: Connection

message_languages: deque


class LogTime:
    """Time measuring context manager, logs time elapsed while executing the context

    Usage:

        with LogTime("<task>"):
            ...

    The above will log: "<task> took X ms".
    """

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.started_at = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.perf_counter() - self.started_at) * 1000
        time_logger = logging.getLogger("time")
        time_logger.info("{name} took {elapsed} ms".format(name=self.name, elapsed=elapsed))


def user_from_update(update: Update):
    if update.message:
        return update.message.from_user
    elif update.callback_query:
        return update.callback_query.from_user
    logger.error(
        "Neither message nor callback_query are defined; returning None.  The update is {}".format(update.to_dict()))
    return None


def update_language_by_code(code: str):
    global _

    translation = gettext.translation("bot", localedir="locales", languages=[code])
    translation.install()

    _ = translation.gettext


def update_language(user: User):
    """Load the translation to match the user language"""

    user_lang = user.language_code if SPEAK_USER_LANGUAGE else DEFAULT_LANGUAGE

    update_language_by_code(user_lang if user_lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE)


def delete_user_record(tg_id):
    """Deletes the user record from the DB"""

    with LogTime("DELETE FROM people WHERE tg_id=?"):
        global db_connection
        c = db_connection.cursor()

        c.execute("DELETE FROM people WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def has_user_record(td_ig):
    with LogTime("SELECT FROM people WHERE tg_id=?"):
        global db_connection
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_username, occupation, location FROM people WHERE tg_id=?", (td_ig,)):
            return True

        return False


def register_good_member(tg_id):
    """Registers the user ID in the antispam_allowlist table"""

    with LogTime("INSERT OR REPLACE INTO antispam_allowlist"):
        global db_connection
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO antispam_allowlist (tg_id) VALUES(?)", (tg_id,))

        db_connection.commit()


def is_good_member(tg_id):
    """Returns whether the user ID exists in the antispam_allowlist table"""

    with LogTime("SELECT FROM antispam_allowlist WHERE tg_id=?"):
        global db_connection
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_id FROM antispam_allowlist WHERE tg_id=?", (tg_id,)):
            return True

        return False


async def delete_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete the message contained in the data of the context job

    This function is called with a delay and is intended to delete a message sent by the bot earlier, and also delete
    the message that the former one was sent in reply to.  It is used to clean automatically the messages that users
    send to the bot in the chat: the intended way to use it is communicating via private messages.

    Use `self_destructing_reply()` as a wrapper for this function."""

    message_to_delete, delete_reply_to = context.job.data

    await context.bot.deleteMessage(message_id=message_to_delete.message_id, chat_id=message_to_delete.chat.id)

    if delete_reply_to:
        await context.bot.deleteMessage(message_id=message_to_delete.reply_to_message.message_id,
                                        chat_id=message_to_delete.chat.id)


async def self_destructing_reply(update, context, message_body, timeout, delete_reply_to=True):
    """Replies to the message contained in the update.  If `timeout` is greater than zero, schedules the reply to be
    deleted."""

    if update.effective_message.chat_id == update.message.from_user.id:
        logger.error("Cannot delete messages in private chats!")
        return

    posted_message = await update.message.reply_text(message_body, parse_mode=ParseMode.HTML)

    if timeout > 0:
        context.job_queue.run_once(delete_message, timeout, data=(posted_message, delete_reply_to))


async def talking_private(update: Update, context) -> bool:
    """Helper for handlers that require private conversation

    Most features of the bot should not be accessed from the chat, instead users should talk to the bot directly via
    private conversation.  This function checks if the update came from the private conversation, and if that is not the
    case, sends a self-destructing reply that suggests talking private.  The caller can simply return if this returned
    false.
    """

    from_user = user_from_update(update)

    if not from_user or update.effective_message.chat_id != from_user.id:
        await self_destructing_reply(update, context, _("MESSAGE_MC_LET_US_TALK_PRIVATE"), DELETE_MESSAGE_TIMEOUT)
        return False
    return True


async def is_member_of_main_chat(user, context):
    """Helper for handlers that require that the user would be a member of the main chat"""

    def should_be_blocked(chat_member: ChatMember):
        if isinstance(chat_member, ChatMemberLeft):
            return "not in chat"
        if isinstance(chat_member, ChatMemberBanned):
            return "banned"
        return None

    reason = should_be_blocked(await context.bot.get_chat_member(MAIN_CHAT_ID, user.id))
    if reason:
        logger.info("User {username} (chat ID {chat_id}) is not allowed: {reason}".format(username=user.username,
                                                                                          chat_id=user.id,
                                                                                          reason=reason))
        return False

    return True


def get_standard_keyboard(tg_id, hidden_commands=None):
    """Builds the standard keyboard for the user identified by `td_id`

    The standard keyboard looks like this:

    +-----------------+
    | WHO             |
    +--------+--------+
    | ENROLL | RETIRE |
    +--------+--------+

    Depending on the context, certain commands can be omitted.

    Returns an instance of InlineKeyboardMarkup.
    """

    command_buttons = {_("BUTTON_WHO"): COMMAND_WHO, _("BUTTON_ENROLL"): COMMAND_ENROLL,
                       _("BUTTON_UPDATE"): COMMAND_ENROLL, _("BUTTON_RETIRE"): COMMAND_RETIRE}
    button_who, button_enroll, button_update, button_retire = (InlineKeyboardButton(text, callback_data=command) for
                                                               text, command in command_buttons.items())

    if hidden_commands is None:
        hidden_commands = list()
    buttons = []
    if COMMAND_WHO not in hidden_commands:
        buttons.append([button_who])

    enrolled = tg_id != 0 and has_user_record(tg_id)
    second_row = []
    if COMMAND_ENROLL not in hidden_commands:
        second_row.append(button_update if enrolled else button_enroll)
    if enrolled and COMMAND_RETIRE not in hidden_commands:
        second_row.append(button_retire)
    if second_row:
        buttons.append(second_row)

    return InlineKeyboardMarkup(buttons)


def get_yesno_keyboard():
    """Builds the YES/NO keyboard used in the step where the user confirms legality of their service

    +-----+----+
    | YES | NO |
    +-----+----+

    Returns an instance of InlineKeyboardMarkup.
    """

    response_buttons = {_("BUTTON_YES"): RESPONSE_YES, _("BUTTON_NO"): RESPONSE_NO}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data=command) for text, command in
                                               response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


def get_moderation_keyboard(tg_id):
    response_buttons = {_("BUTTON_YES"): MODERATOR_APPROVE, _("BUTTON_NO"): MODERATOR_DECLINE}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data="{}:{}".format(command, tg_id))
                                               for text, command in response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


# noinspection PyUnusedLocal
async def moderate_new_data(update: Update, context: ContextTypes.DEFAULT_TYPE, data) -> None:
    moderator_ids = MODERATOR_IDS if MODERATOR_IDS else (DEVELOPER_CHAT_ID,)

    for moderator_id in moderator_ids:
        logger.info("Sending moderation request to moderator ID {id}".format(id=moderator_id))
        await context.bot.send_message(chat_id=moderator_id,
                                       text=_("MESSAGE_ADMIN_APPROVE_USER_DATA {username}").format(
                                           username=data["tg_username"], occupation=data["occupation"],
                                           location=data["location"]),
                                       reply_markup=get_moderation_keyboard(data["tg_id"]))


async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the welcome message to the user that has just joined the main chat"""

    for user in update.message.new_chat_members:
        if user.is_bot:
            continue

        update_language(user)

        logger.info("Greeting new user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

        greeting_message = _("MESSAGE_MC_GREETING_M {user_first_name} {bot_first_name}") if BOT_IS_MALE else _(
            "MESSAGE_MC_GREETING_F {user_first_name} {bot_first_name}")

        await self_destructing_reply(update, context, greeting_message.format(user_first_name=user.first_name,
                                                                              bot_first_name=context.bot.first_name),
                                     GREETING_TIMEOUT, False)


async def detect_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect language of the incoming message in the main chat, and show a warning if there are too many messages
    written in non-default languages."""

    if (update.effective_message.chat_id != MAIN_CHAT_ID or
            not hasattr(update.message, "text") or
            len(update.message.text.split(" ")) < LANGUAGE_MODERATION_MIN_WORD_COUNT):
        return

    global message_languages

    message_languages.append(detect(update.message.text))

    if len(message_languages) < LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT:
        return

    while len(message_languages) > LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT:
        message_languages.popleft()

    if DEFAULT_LANGUAGE not in message_languages:
        update_language_by_code(DEFAULT_LANGUAGE)
        message_languages = deque()
        await context.bot.send_message(chat_id=MAIN_CHAT_ID, text=_("MESSAGE_MC_SPEAK_DEFAULT_LANGUAGE"), parse_mode=ParseMode.HTML)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the help message"""

    user = update.message.from_user

    update_language(user)

    if update.effective_message.chat_id != user.id:
        await self_destructing_reply(update, context, _("MESSAGE_MC_HELP"), DELETE_MESSAGE_TIMEOUT)
        return

    if not await is_member_of_main_chat(user, context):
        return

    await update.message.reply_text(_("MESSAGE_DM_HELP"), reply_markup=get_standard_keyboard(user.id))


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and show them the selection of options"""

    user = update.message.from_user

    update_language(user)

    if user.id == DEVELOPER_CHAT_ID and update.message.chat.id != DEVELOPER_CHAT_ID:
        logger.info("This is the admin user {username} talking from \"{chat_name}\" (chat ID {chat_id})".format(
            username=user.username, chat_name=update.message.chat.title, chat_id=update.message.chat.id))

        await context.bot.deleteMessage(message_id=update.message.id, chat_id=update.message.chat.id)

        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID,
                                       text=_("MESSAGE_ADMIN_MAIN_CHAT_ID {title} {id}").format(
                                           title=update.message.chat.title, id=str(update.message.chat.id)))

        return

    if not await talking_private(update, context):
        return

    if not await is_member_of_main_chat(user, context):
        return

    logger.info("Welcoming user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

    main_chat = await context.bot.get_chat(MAIN_CHAT_ID)

    await update.message.reply_text(
        _("MESSAGE_DM_HELLO {bot_first_name} {main_chat_name}").format(bot_first_name=context.bot.first_name,
                                                                       main_chat_name=main_chat.title),
        reply_markup=get_standard_keyboard(user.id))


# noinspection PyUnusedLocal
async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current registry"""

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()

    user_list = [_("MESSAGE_DM_WHO_LIST_HEADING")]

    with LogTime("SELECT FROM people"):
        global db_connection
        c = db_connection.cursor()

        for row in c.execute("SELECT tg_id, tg_username, occupation, location FROM people WHERE is_suspended=0"):
            values = {key: value for (key, value) in zip((i[0] for i in c.description), row)}
            user_list.append("@{username} ({location}): {occupation}".format(username=values["tg_username"],
                                                                             occupation=values["occupation"],
                                                                             location=values["location"]))

        if len(user_list) == 1:
            user_list = [_("MESSAGE_DM_WHO_EMPTY")]

    await query.edit_message_reply_markup(None)
    await query.message.reply_text(text="\n".join(user_list), reply_markup=get_standard_keyboard(query.from_user.id))


# noinspection PyUnusedLocal
async def enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()
    await query.edit_message_reply_markup(None)

    if not query.from_user.username:
        await query.message.reply_text(_("MESSAGE_DM_ENROLL_USERNAME_REQUIRED"),
                                       reply_markup=get_standard_keyboard(query.from_user.id))
        return ConversationHandler.END

    await query.message.reply_text(_("MESSAGE_DM_ENROLL_ASK_OCCUPATION"))

    return TYPING_OCCUPATION


async def received_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    update_language(update.message.from_user)

    user_data = context.user_data
    user_data["occupation"] = update.message.text

    await update.message.reply_text(_("MESSAGE_DM_ENROLL_ASK_LOCATION"))

    return TYPING_LOCATION


async def received_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the legality"""

    update_language(update.message.from_user)

    user_data = context.user_data
    user_data["location"] = update.message.text

    await update.message.reply_text(_("MESSAGE_DM_ENROLL_CONFIRM_LEGALITY"), reply_markup=get_yesno_keyboard())

    return CONFIRMING_LEGALITY


async def confirm_legality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Complete the enrollment"""

    query = update.callback_query
    from_user = query.from_user

    update_language(from_user)

    await query.answer()

    user_data = context.user_data

    if query.data == RESPONSE_YES:
        with LogTime("INSERT OR REPLACE INTO people"):
            global db_connection
            c = db_connection.cursor()

            c.execute("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, location, is_suspended) "
                      "VALUES(?, ?, ?, ?, ?)", (
                      from_user.id, from_user.username, user_data["occupation"], user_data["location"],
                      (0 if MODERATION_IS_LAZY else 1)))

            db_connection.commit()
        saved_user_data = copy.deepcopy(user_data)
        user_data.clear()

        saved_user_data["tg_id"] = from_user.id
        saved_user_data["tg_username"] = from_user.username

        await query.edit_message_reply_markup(None)

        if not MODERATION_ENABLED:
            message = _("MESSAGE_DM_ENROLL_COMPLETED")
        elif MODERATION_IS_LAZY:
            message = _("MESSAGE_DM_ENROLL_COMPLETED_POST_MODERATION")
        else:
            message = _("MESSAGE_DM_ENROLL_COMPLETED_PRE_MODERATION")

        await query.message.reply_text(message, reply_markup=get_standard_keyboard(from_user.id))

        if MODERATION_ENABLED:
            await moderate_new_data(update, context, saved_user_data)

    elif query.data == RESPONSE_NO:
        delete_user_record(from_user.id)
        user_data.clear()

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(_("MESSAGE_DM_ENROLL_DECLINED_ILLEGAL_SERVICE"),
                                       reply_markup=get_standard_keyboard(0, [COMMAND_RETIRE]))

    return ConversationHandler.END


async def detect_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect spam and take appropriate action"""

    if update.effective_message is None:
        logger.warning("The update does not have any message, cannot detect spam")
        return
    message = update.effective_message

    if message.chat_id != MAIN_CHAT_ID:
        logger.info("The message does not belong to the main chat, will not detect spam")
        return

    if not hasattr(message, "text"):
        logger.info("The message does not have text, cannot detect spam")
        return

    update_language(message.from_user)

    if is_good_member(message.from_user.id):
        return

    logger.info("User ID {user_id} posts their first message".format(user_id=message.from_user.id))

    found_spam = False

    if ANTISPAM_STOP_WORDS_ENABLED:
        if antispam.detect_stop_words(message.text):
            logger.info("SPAM detected by stop words in the first message from user ID {user_id}".format(
                user_id=message.from_user.id))
            found_spam = True

    if not found_spam and ANTISPAM_OPENAI_ENABLED:
        if antispam.detect_openai(message.text, ANTISPAM_OPENAI_API_KEY):
            logger.info("SPAM detected by OpenAI in the first message from user ID {user_id}".format(
                user_id=message.from_user.id))
            found_spam = True

    if found_spam:
        admins = " ".join("@" + admin for admin in ADMIN_USERNAMES)
        await message.reply_text(text=_("MESSAGE_MC_SPAM_DETECTED").format(admins=admins))
        return

    logger.info("Nothing wrong with this message.")
    register_good_member(message.from_user.id)


# noinspection PyUnusedLocal
async def confirm_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Approve or decline changes to user data"""

    global db_connection

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()

    command, tg_id = query.data.split(":")

    if command == MODERATOR_APPROVE:
        logger.info("Moderator ID {moderator_id} approves new data from user ID {user_id}".format(
            moderator_id=query.from_user.id, user_id=tg_id))

        if not MODERATION_IS_LAZY:
            with LogTime("UPDATE people"):
                c = db_connection.cursor()

                c.execute("UPDATE people SET is_suspended=0 WHERE tg_id=?", (tg_id,))

                db_connection.commit()

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(_("MESSAGE_ADMIN_USER_RECORD_APPROVED"))
    elif command == MODERATOR_DECLINE:
        logger.info("Moderator ID {moderator_id} declines new data from user ID {user_id}".format(
            moderator_id=query.from_user.id, user_id=tg_id))

        if MODERATION_IS_LAZY:
            with LogTime("UPDATE people"):
                c = db_connection.cursor()

                c.execute("UPDATE people SET is_suspended=1 WHERE tg_id=?", (tg_id,))

                db_connection.commit()

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(_("MESSAGE_ADMIN_USER_RECORD_SUSPENDED"))
    else:
        logger.error("Unexpected query data: '{}'".format(query.data))

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def retire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the user from the directory"""

    query = update.callback_query

    update_language(query.from_user)

    delete_user_record(query.from_user.id)

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(_("MESSAGE_DM_RETIRE"), reply_markup=get_standard_keyboard(0, [COMMAND_RETIRE]))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer"""

    if not isinstance(update, Update):
        logger.error("Unexpected type of update: {}".format(type(update)))
        return

    from_user = user_from_update(update)

    update_language(from_user)

    exception = context.error

    if isinstance(exception, httpx.RemoteProtocolError):
        # Connection errors occur every now and then, and they are caused by reasons external to the bot, so it makes no
        # sense notifying the developer about them.  Log an error and bail out.
        logger.error(exception)
        return

    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=exception)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_string = "".join(traceback.format_exception(None, exception, exception.__traceback__))

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    error_message = (f"<pre>{html.escape(tb_string)}</pre>"
                     f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
                     f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
                     f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n")

    # Finally, send the message
    await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=error_message, parse_mode=ParseMode.HTML)

    if not await talking_private(update, context):
        return

    if update.message:
        message = update.message
    elif update.callback_query:
        message = update.callback_query.message
    else:
        logger.error("Unexpected state of the update: {}".format(update_str))
        return

    await message.reply_text(_("MESSAGE_DM_INTERNAL_ERROR"), reply_markup=get_standard_keyboard(from_user.id))


def main() -> None:
    """Run the bot"""

    global db_connection
    db_connection = sqlite3.connect("people.db")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler(COMMAND_START, hello))
    application.add_handler(CommandHandler(COMMAND_HELP, show_help))
    application.add_handler(CallbackQueryHandler(who, pattern=COMMAND_WHO))
    application.add_handler(CallbackQueryHandler(retire, pattern=COMMAND_RETIRE))

    # Add conversation handler that questions the user about his profile
    application.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(enroll, pattern=COMMAND_ENROLL)],
                                                states={TYPING_OCCUPATION: [
                                                    MessageHandler(filters.TEXT, received_occupation)],
                                                    TYPING_LOCATION: [MessageHandler(filters.TEXT, received_location)],
                                                    CONFIRMING_LEGALITY: [CallbackQueryHandler(confirm_legality)]},
                                                fallbacks=[]))

    if GREETING_ENABLED:
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))

    if ANTISPAM_ENABLED:
        application.add_handler(MessageHandler(filters.TEXT, detect_spam), group=1)

    if MODERATION_ENABLED:
        application.add_handler(CallbackQueryHandler(confirm_user_data, pattern=re.compile(
            "^({approve}|{decline}):[0-9]+$".format(approve=MODERATOR_APPROVE, decline=MODERATOR_DECLINE))), group=2)

    if LANGUAGE_MODERATION_ENABLED:
        global message_languages
        message_languages = deque()

        application.add_handler(MessageHandler(filters.TEXT, detect_language), group=3)

    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    db_connection.close()


if __name__ == "__main__":
    main()
