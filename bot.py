#!./venv/bin/python

"""
This is the main script that contains the entry point of the bot.  Execute this file to run the bot.

See README.md for details.
"""

import copy
import gettext
import html
import io
import json
import logging
import re
import time
import traceback
from collections import deque

import httpx
from langdetect import detect, lang_detect_exception
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, User, MenuButtonCommands, BotCommand
from telegram.constants import ParseMode, ChatType
from telegram.ext import (Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters,
                          CallbackQueryHandler, )

from common import db
from common.checks import is_member_of_main_chat
from features import antispam
from settings import *

# Configure logging
# Set higher logging level for httpx to avoid all GET and POST requests being logged.
# noinspection SpellCheckingInspection
logging.basicConfig(format="[%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d] %(message)s",
                    level=logging.INFO, filename="bot.log")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Commands, sequences, and responses
COMMAND_START, COMMAND_HELP, COMMAND_WHO, COMMAND_ENROLL, COMMAND_RETIRE = ("start", "help", "who", "enroll", "retire")
COMMAND_ADMIN = "admin"
SELECTING_CATEGORY, TYPING_OCCUPATION, TYPING_LOCATION, CONFIRMING_LEGALITY = range(4)
UPLOADING_ANTISPAM_KEYWORDS, UPLOADING_ANTISPAM_OPENAI = range(2)
RESPONSE_YES, RESPONSE_NO = ("yes", "no")
MODERATOR_APPROVE, MODERATOR_DECLINE = ("approve", "decline")
(QUERY_ADMIN_DOWNLOAD_SPAM, QUERY_ADMIN_DOWNLOAD_ANTISPAM_KEYWORDS, QUERY_ADMIN_UPLOAD_ANTISPAM_KEYWORDS,
 QUERY_ADMIN_UPLOAD_ANTISPAM_OPENAI) = (
    "download-spam", "download-antispam-keywords", "upload-antispam-keywords", "upload-antispam-openai")

# Global translation context.  Updated by update_language() depending on the locale of the current user.
_ = gettext.gettext

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


def update_language_by_code(code: str):
    global _

    translation = gettext.translation("bot", localedir="locales", languages=[code])
    translation.install()

    _ = translation.gettext


def update_language(user: User):
    """Load the translation to match the user language"""

    user_lang = user.language_code if SPEAK_USER_LANGUAGE else DEFAULT_LANGUAGE

    update_language_by_code(user_lang if user_lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE)


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


async def self_destructing_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, message_body: str, timeout: int,
                                 delete_reply_to=True):
    """Replies to the message contained in the update.  If `timeout` is greater than zero, schedules the reply to be
    deleted."""

    if update.effective_message.chat_id == update.message.from_user.id:
        logger.error("Cannot delete messages in private chats!")
        return

    posted_message = await update.message.reply_text(message_body, parse_mode=ParseMode.HTML)

    if timeout > 0:
        context.job_queue.run_once(delete_message, timeout, data=(posted_message, delete_reply_to))


async def talking_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Helper for handlers that require private conversation

    Most features of the bot should not be accessed from the chat, instead users should talk to the bot directly via
    private conversation.  This function checks if the update came from the private conversation, and if that is not the
    case, sends a self-destructing reply that suggests talking private.  The caller can simply return if this returned
    false.
    """

    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await self_destructing_reply(update, context, _("MESSAGE_MC_LET_US_TALK_PRIVATE"), DELETE_MESSAGE_TIMEOUT)
        return False
    return True


def get_standard_keyboard(tg_id: int, hidden_commands=None):
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

    enrolled = tg_id != 0 and db.people_exists(tg_id)
    second_row = []
    if COMMAND_ENROLL not in hidden_commands:
        second_row.append(button_update if enrolled else button_enroll)
    if enrolled and COMMAND_RETIRE not in hidden_commands:
        second_row.append(button_retire)
    if second_row:
        buttons.append(second_row)

    return InlineKeyboardMarkup(buttons)


def get_category_keyboard():
    """Builds the keyboard for selecting a category when enrolling or updating data

    If there is at least one category in the `people_category` table, returns an instance of InlineKeyboardMarkup that
    contains a vertically aligned set of buttons:

    +------------+
    | Category 1 |
    +------------+
    | Category 2 |
    +------------+
    | ...        |
    +------------+
    | Default    |
    +------------+

    Each button has the category ID in its callback data.  The "Default" item means "no category", its callback data is
    set to 0.

    If no categories are defined in the DB, this function returns None.
    """

    buttons = []
    for category in db.people_category_select_all():
        buttons.append((InlineKeyboardButton(category["title"], callback_data=category["id"]),))
    if not buttons:
        return None
    buttons.append((InlineKeyboardButton(_("BUTTON_ENROLL_CATEGORY_DEFAULT"), callback_data=0),))
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


def get_moderation_keyboard(tg_id: int):
    response_buttons = {_("BUTTON_YES"): MODERATOR_APPROVE, _("BUTTON_NO"): MODERATOR_DECLINE}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data="{}:{}".format(command, tg_id))
                                               for text, command in response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


def get_admin_keyboard() -> InlineKeyboardMarkup:
    response_buttons = {_("BUTTON_DOWNLOAD_SPAM"): QUERY_ADMIN_DOWNLOAD_SPAM,
                        _("BUTTON_DOWNLOAD_ANTISPAM_KEYWORDS"): QUERY_ADMIN_DOWNLOAD_ANTISPAM_KEYWORDS,
                        _("BUTTON_UPLOAD_ANTISPAM_KEYWORDS"): QUERY_ADMIN_UPLOAD_ANTISPAM_KEYWORDS,
                        _("BUTTON_UPLOAD_ANTISPAM_OPENAI"): QUERY_ADMIN_UPLOAD_ANTISPAM_OPENAI}
    button_download_spam, button_download_keywords, button_upload_keywords, button_upload_openai = (
        InlineKeyboardButton(text, callback_data=command) for text, command in response_buttons.items())

    return InlineKeyboardMarkup(
        ((button_download_spam,), (button_download_keywords,), (button_upload_keywords,), (button_upload_openai,)))


# noinspection PyUnusedLocal
async def moderate_new_data(update: Update, context: ContextTypes.DEFAULT_TYPE, data) -> None:
    moderator_ids = ADMINISTRATORS.keys() if ADMINISTRATORS else (DEVELOPER_CHAT_ID,)

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

    if (update.effective_message.chat_id != MAIN_CHAT_ID or not hasattr(update.message, "text") or len(
            update.message.text.split(" ")) < LANGUAGE_MODERATION_MIN_WORD_COUNT):
        return

    global message_languages

    try:
        message_languages.append(detect(update.message.text))
    except lang_detect_exception.LangDetectException:
        logger.warning("Caught LangDetectException while processing a message")
        return

    if len(message_languages) < LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT:
        return

    while len(message_languages) > LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT:
        message_languages.popleft()

    if DEFAULT_LANGUAGE not in message_languages:
        update_language_by_code(DEFAULT_LANGUAGE)
        message_languages = deque()
        await context.bot.send_message(chat_id=MAIN_CHAT_ID, text=_("MESSAGE_MC_SPEAK_DEFAULT_LANGUAGE"),
                                       parse_mode=ParseMode.HTML)


async def handle_command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the help message"""

    message = update.effective_message
    user = message.from_user

    update_language(user)

    if message.chat_id != user.id:
        await self_destructing_reply(update, context, _("MESSAGE_MC_HELP"), DELETE_MESSAGE_TIMEOUT)
        return

    if not await is_member_of_main_chat(user, context):
        return

    await message.reply_text(_("MESSAGE_DM_HELP"), reply_markup=get_standard_keyboard(user.id))


async def handle_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and show them the selection of options"""

    message = update.effective_message
    user = message.from_user

    update_language(user)

    if user.id == DEVELOPER_CHAT_ID and message.chat.id != DEVELOPER_CHAT_ID:
        logger.info("This is the admin user {username} talking from \"{chat_name}\" (chat ID {chat_id})".format(
            username=user.username, chat_name=message.chat.title, chat_id=message.chat.id))

        await context.bot.deleteMessage(message_id=message.id, chat_id=message.chat.id)
        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID,
                                       text=_("MESSAGE_ADMIN_MAIN_CHAT_ID {title} {id}").format(
                                           title=message.chat.title, id=str(message.chat.id)))
        return

    if not await talking_private(update, context):
        return

    if MAIN_CHAT_ID == 0:
        logger.info("Welcoming user {username} (chat ID {chat_id}), is this the admin?".format(
            username=user.username, chat_id=user.id))
        return

    if not await is_member_of_main_chat(user, context):
        return

    logger.info("Welcoming user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

    main_chat = await context.bot.get_chat(MAIN_CHAT_ID)

    await message.reply_text(
        _("MESSAGE_DM_HELLO {bot_first_name} {main_chat_name}").format(bot_first_name=context.bot.first_name,
                                                                       main_chat_name=main_chat.title),
        reply_markup=get_standard_keyboard(user.id))


async def handle_command_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the admin menu"""

    message = update.effective_message
    user = message.from_user

    if user.id not in ADMINISTRATORS.keys():
        logging.info("User {username} tried to invoke the admin UI".format(username=user.username))
        return

    if not await talking_private(update, context):
        await context.bot.deleteMessage(message_id=message.id, chat_id=message.chat.id)

    update_language(user)
    await context.bot.send_message(chat_id=user.id, text=_("MESSAGE_DM_ADMIN"), reply_markup=get_admin_keyboard())


# noinspection PyUnusedLocal
async def handle_query_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> [None, int]:
    query = update.callback_query
    user = query.from_user

    if user.id not in ADMINISTRATORS.keys():
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    update_language(user)

    if query.data == QUERY_ADMIN_DOWNLOAD_SPAM:
        spam = [record for record in db.spam_select_all()]
        await user.send_document(json.dumps(spam, ensure_ascii=False, indent=2).encode("utf-8"), filename="spam.json",
                                 reply_markup=None)
    elif query.data == QUERY_ADMIN_DOWNLOAD_ANTISPAM_KEYWORDS:
        await user.send_document(antispam.get_keywords(), filename="bad_keywords.txt", reply_markup=None)
    elif query.data == QUERY_ADMIN_UPLOAD_ANTISPAM_KEYWORDS:
        await query.message.reply_text(_("MESSAGE_DM_ADMIN_REQUEST_KEYWORDS"))

        return UPLOADING_ANTISPAM_KEYWORDS
    elif query.data == QUERY_ADMIN_UPLOAD_ANTISPAM_OPENAI:
        await query.message.reply_text(_("MESSAGE_DM_ADMIN_REQUEST_OPENAI"))

        return UPLOADING_ANTISPAM_OPENAI


# noinspection PyUnusedLocal
async def received_antispam_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in ADMINISTRATORS.keys():
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return ConversationHandler.END

    document = update.message.effective_attachment

    if document.mime_type != "text/plain":
        await update.effective_message.reply_text(_("MESSAGE_DM_ADMIN_KEYWORDS_WRONG_FILE_TYPE"),
                                                  reply_markup=get_admin_keyboard())
        return ConversationHandler.END

    keywords_file = await document.get_file()
    data = io.BytesIO()
    await keywords_file.download_to_memory(data)

    if antispam.save_new_keywords(data):
        await update.effective_message.reply_text(_("MESSAGE_DM_ADMIN_KEYWORDS_UPDATED"), reply_markup=None)
    else:
        await update.effective_message.reply_text(_("MESSAGE_DM_ADMIN_KEYWORDS_CANNOT_USE"),
                                                  reply_markup=get_admin_keyboard())

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def received_antispam_openai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in ADMINISTRATORS.keys():
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return ConversationHandler.END

    document = update.message.effective_attachment

    openai_file = await document.get_file()
    data = io.BytesIO()
    await openai_file.download_to_memory(data)

    if antispam.save_new_openai(data):
        await update.effective_message.reply_text(_("MESSAGE_DM_ADMIN_OPENAI_UPDATED"), reply_markup=None)
    else:
        await update.effective_message.reply_text(_("MESSAGE_DM_ADMIN_OPENAI_CANNOT_USE"),
                                                  reply_markup=get_admin_keyboard())

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current registry"""

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()

    user_list = [_("MESSAGE_DM_WHO_LIST_HEADING")]

    categorised_people = {0: {"title": _("MESSAGE_DM_WHO_CATEGORY_DEFAULT"), "people": []}}

    for category in db.people_category_select_all():
        categorised_people[category["id"]] = {"title": category["title"], "people": []}

    for person in db.people_select_all():
        if "category_id" not in person or person["category_id"] not in categorised_people:
            person["category_id"] = 0
        categorised_people[person["category_id"]]["people"].append(person)

    filtered_people = [{"title": c["title"], "people": c["people"]} for i, c in categorised_people.items() if
                       i != 0 and c["people"]]
    if categorised_people[0]["people"]:
        filtered_people.append(categorised_people[0])

    def people_to_message(people):
        for p in people:
            user_list.append("@{username} ({location}): {occupation}".format(username=p["tg_username"],
                                                                             occupation=p["occupation"],
                                                                             location=p["location"]))

    if len(filtered_people) == 1:
        people_to_message(filtered_people[0]["people"])
    else:
        for category in filtered_people:
            user_list.append("")
            user_list.append("<b>{t}</b>".format(t=category["title"]))
            people_to_message(category["people"])

    if len(user_list) == 1:
        user_list = [_("MESSAGE_DM_WHO_EMPTY")]

    await query.edit_message_reply_markup(None)
    await query.message.reply_text(text="\n".join(user_list), reply_markup=get_standard_keyboard(query.from_user.id),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True)


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

    await query.message.reply_text(_("MESSAGE_DM_ENROLL_START"))

    category_buttons = get_category_keyboard()

    if category_buttons:
        await query.message.reply_text(_("MESSAGE_DM_ENROLL_ASK_CATEGORY"),
                                       reply_markup=get_category_keyboard())

        return SELECTING_CATEGORY
    else:
        user_data = context.user_data
        user_data["category_id"] = 0

        await query.message.reply_text(_("MESSAGE_DM_ENROLL_ASK_OCCUPATION"))

        return TYPING_OCCUPATION


async def received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    query = update.callback_query

    update_language(query.from_user)

    user_data = context.user_data
    user_data["category_id"] = query.data

    await query.answer()
    await query.edit_message_reply_markup(None)

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
        db.people_insert_or_update(from_user.id, from_user.username, user_data["occupation"], user_data["location"],
                                   (0 if MODERATION_IS_LAZY else 1), user_data["category_id"])

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
        db.people_delete(from_user.id)
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
    user = message.from_user

    if message.chat_id != MAIN_CHAT_ID:
        # The message does not belong to the main chat, will not detect spam.
        return

    if db.is_good_member(user.id):
        # The message comes from a known user, will not detect spam.
        return

    try:
        if not antispam.is_spam(message):
            logger.info(
                "The first message from user {full_name} (ID {id}) looks good".format(full_name=user.full_name,
                                                                                      id=user.id))
            db.register_good_member(user.id)
            return
    except Exception as e:
        logger.error("Exception while trying to detect spam:", exc_info=e)

        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=str(e))
        return

    await context.bot.deleteMessage(message_id=message.id, chat_id=message.chat.id)

    update_language_by_code(DEFAULT_LANGUAGE)

    if BOT_IS_MALE:
        delete_notice = _("MESSAGE_MC_SPAM_DETECTED_M {username}")
    else:
        delete_notice = _("MESSAGE_MC_SPAM_DETECTED_F {username}")

    posted_message = await context.bot.send_message(MAIN_CHAT_ID,
                                                    delete_notice.format(username=message.from_user.full_name),
                                                    disable_notification=True)
    context.job_queue.run_once(delete_message, 15, data=(posted_message, False))


# noinspection PyUnusedLocal
async def confirm_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Approve or decline changes to user data"""

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()

    command, tg_id = query.data.split(":")
    tg_id = int(tg_id)

    if command == MODERATOR_APPROVE:
        logger.info("Moderator ID {moderator_id} approves new data from user ID {user_id}".format(
            moderator_id=query.from_user.id, user_id=tg_id))

        if not MODERATION_IS_LAZY:
            db.people_approve(tg_id)

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(_("MESSAGE_ADMIN_USER_RECORD_APPROVED"))
    elif command == MODERATOR_DECLINE:
        logger.info("Moderator ID {moderator_id} declines new data from user ID {user_id}".format(
            moderator_id=query.from_user.id, user_id=tg_id))

        if MODERATION_IS_LAZY:
            db.people_suspend(tg_id)

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

    db.people_delete(query.from_user.id)

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(_("MESSAGE_DM_RETIRE"), reply_markup=get_standard_keyboard(0, [COMMAND_RETIRE]))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer"""

    if not isinstance(update, Update):
        logger.error("Unexpected type of update: {}".format(type(update)))
        return

    user = update.effective_message.from_user

    update_language(user)

    exception = context.error

    if isinstance(exception, httpx.RemoteProtocolError):
        # Connection errors happen regularly, and they are caused by reasons external to the bot, so it makes no
        # sense notifying the developer about them.  Log an error and bail out.
        logger.error(exception)
        return

    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=exception)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_string = "".join(traceback.format_exception(None, exception, exception.__traceback__))

    # Build the message with some markup and additional information about what happened.
    # TODO: add logic to deal with messages longer than 4096 characters (Telegram has that limit).
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

    await message.reply_text(_("MESSAGE_DM_INTERNAL_ERROR"), reply_markup=get_standard_keyboard(user.id))


async def post_init(application: Application) -> None:
    bot = application.bot

    update_language_by_code(DEFAULT_LANGUAGE)

    await bot.set_my_commands([BotCommand(command=COMMAND_START, description=_("COMMAND_DESCRIPTION_START")),
                               BotCommand(command=COMMAND_ADMIN, description=_("COMMAND_DESCRIPTION_ADMIN"))])

    for chat_id in ADMINISTRATORS.keys():
        await bot.set_chat_menu_button(chat_id, MenuButtonCommands())


def main() -> None:
    """Run the bot"""

    db.connect()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler(COMMAND_START, handle_command_start))
    application.add_handler(CommandHandler(COMMAND_HELP, handle_command_help))
    application.add_handler(CommandHandler(COMMAND_ADMIN, handle_command_admin))

    application.add_handler(CallbackQueryHandler(who, pattern=COMMAND_WHO))
    application.add_handler(CallbackQueryHandler(retire, pattern=COMMAND_RETIRE))

    application.add_handler(CallbackQueryHandler(handle_query_admin, pattern=QUERY_ADMIN_DOWNLOAD_SPAM))
    application.add_handler(CallbackQueryHandler(handle_query_admin, pattern=QUERY_ADMIN_DOWNLOAD_ANTISPAM_KEYWORDS))
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_query_admin, pattern=QUERY_ADMIN_UPLOAD_ANTISPAM_KEYWORDS)],
        states={UPLOADING_ANTISPAM_KEYWORDS: [MessageHandler(filters.ATTACHMENT, received_antispam_keywords)]},
        fallbacks=[]))
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_query_admin, pattern=QUERY_ADMIN_UPLOAD_ANTISPAM_OPENAI)],
        states={UPLOADING_ANTISPAM_OPENAI: [MessageHandler(filters.ATTACHMENT, received_antispam_openai)]},
        fallbacks=[]))

    # Add conversation handler that questions the user about his profile
    application.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(enroll, pattern=COMMAND_ENROLL)],
                                                states={SELECTING_CATEGORY: [CallbackQueryHandler(received_category)],
                                                        TYPING_OCCUPATION: [
                                                            MessageHandler(filters.TEXT, received_occupation)],
                                                        TYPING_LOCATION: [
                                                            MessageHandler(filters.TEXT, received_location)],
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

    db.disconnect()


if __name__ == "__main__":
    main()
