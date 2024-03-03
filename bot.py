#!./venv/bin/python

"""
See README.md for details
"""

import gettext
import html
import json
import logging
import sqlite3
import time
import traceback
from sqlite3 import Connection

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, User, ChatMemberLeft, ChatMemberBanned, \
    ChatMember
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters,
                          CallbackQueryHandler, )

from secret import BOT_TOKEN, DEVELOPER_CHAT_ID, MAIN_CHAT_ID

# Supported languages.  Every time a new translation is added, this tuple should be updated.
LANGUAGES = ('en', 'ru')

# Configure logging
# Set higher logging level for httpx to avoid all GET and POST requests being logged.
logging.basicConfig(format="[%(asctime)s] %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Timeout for the self-destructible messages (in seconds)
DELETE_MESSAGE_TIMEOUT = 60

# Commands, sequences, and responses
COMMAND_START, COMMAND_HELP, COMMAND_WHO, COMMAND_ENROLL, COMMAND_RETIRE = ("start", "help", "who", "enroll", "retire")
TYPING_OCCUPATION, TYPING_LOCATION, CONFIRMING_LEGALITY = range(3)
RESPONSE_YES, RESPONSE_NO = ("yes", "no")

# Global translation context.  Updated by update_language() depending on the locale of the current user.
_ = gettext.gettext

db_connection: Connection


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
        logger.info("{name} took {elapsed} ms".format(name=self.name, elapsed=elapsed))


def update_language(user: User):
    """Load the translation to match the user language"""

    global _

    user_lang = user.language_code
    translation = gettext.translation('bot', localedir='locales',
                                      languages=[user_lang if user_lang in LANGUAGES else 'en'])
    translation.install()

    _ = translation.gettext


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


async def delete_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete the message contained in the data of the context job

    This function is called with a delay and is intended to delete a message sent by the bot earlier, and also delete
    the message that the former one was sent in reply to.  It is used to clean automatically the messages that users
    send to the bot in the chat: the intended way to use it is communicating via private messages.

    Use `self_destructing_reply()` as a wrapper for this function."""

    for message_to_delete in (context.job.data, context.job.data.reply_to_message):
        await context.bot.deleteMessage(message_id=message_to_delete.message_id, chat_id=message_to_delete.chat.id)


async def self_destructing_reply(update, context, message_body):
    """Replies to the message contained in the update, then schedules the reply to be deleted"""

    if update.effective_message.chat_id == update.message.from_user.id:
        logger.error("Cannot delete messages in private chats!")
        return

    posted_message = await update.message.reply_text(message_body)

    context.job_queue.run_once(delete_message, DELETE_MESSAGE_TIMEOUT, data=posted_message)


async def talking_private(update, context) -> bool:
    """Helper for handlers that require private conversation

    Most features of the bot should not be accessed from the chat, instead users should talk to the bot directly via
    private conversation.  This function checks if the update came from the private conversation, and if that is not the
    case, sends a self-destructing reply that suggests talking private.  The caller can simply return if this returned
    false.
    """

    if update.effective_message.chat_id != update.message.from_user.id:
        await self_destructing_reply(update, context, _("Let's talk private!"))
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

    command_buttons = {_("Show records"): COMMAND_WHO, _("Register yourself"): COMMAND_ENROLL,
                       _("Update your record"): COMMAND_ENROLL, _("Remove your record"): COMMAND_RETIRE}
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

    response_buttons = {_("Yes"): RESPONSE_YES, _("No"): RESPONSE_NO}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data=command) for text, command in
                                               response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the help message"""

    user = update.message.from_user

    update_language(user)

    if update.effective_message.chat_id != user.id:
        await self_destructing_reply(update, context,
                                     _("I keep records of users who would like to offer something to others, "
                                       "and provide that information to everyone in this chat.\n"
                                       "\n"
                                       "To learn more and see what I can do, start a private conversation with me.\n"
                                       "\n"
                                       "I will delete this message in a minute to keep this chat clean of my "
                                       "messages."))
        return

    if not await is_member_of_main_chat(user, context):
        return

    await update.message.reply_text(_("I keep records of users of the chat who would like to offer something to "
                                      "others, and provide that information to everyone in the chat.\n"
                                      "\n"
                                      "The data is simple: every person tells what they do and where they are based.  "
                                      "I keep no personal data, only Telegram usernames of those who register.\n"
                                      "\n"
                                      "Use the buttons below to see the records, to add yourself or update your data, "
                                      "and to remove your record (of course if you have one)."),
                                    reply_markup=get_standard_keyboard(user.id))


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and show them the selection of options"""

    user = update.message.from_user

    update_language(user)

    if user.id == DEVELOPER_CHAT_ID and update.message.chat.id != DEVELOPER_CHAT_ID:
        logger.info("This is the admin user {username} talking from \"{chat_name}\" (chat ID {chat_id})".format(
            username=user.username, chat_name=update.message.chat.title, chat_id=update.message.chat.id))

        await context.bot.deleteMessage(message_id=update.message.id, chat_id=update.message.chat.id)

        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID,
                                       text=_("The ID of the \"{title}\" group is {id}").format(
                                           title=update.message.chat.title, id=str(update.message.chat.id)))

        return

    if not await talking_private(update, context):
        return

    if not await is_member_of_main_chat(user, context):
        return

    logger.info("Welcoming user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

    main_chat = await context.bot.get_chat(MAIN_CHAT_ID)

    await update.message.reply_text(
        _("Hello!  I am {bot_name}, the bookkeeper bot of the \"{main_chat_name}\" group.").format(
            bot_name=context.bot.first_name, main_chat_name=main_chat.title),
        reply_markup=get_standard_keyboard(user.id))


async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current registry"""

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()

    user_list = [_("Here is the directory:")]

    with LogTime("SELECT FROM people"):
        global db_connection
        c = db_connection.cursor()

        for row in c.execute("SELECT tg_id, tg_username, occupation, location FROM people"):
            values = {key: value for (key, value) in zip((i[0] for i in c.description), row)}
            user_list.append("@{username} ({location}): {occupation}".format(username=values["tg_username"],
                                                                             occupation=values["occupation"],
                                                                             location=values["location"]))

        if len(user_list) == 1:
            user_list = [_("Nobody has registered themselves so far :-( .")]

    await query.edit_message_reply_markup(None)
    await query.message.reply_text(text="\n".join(user_list), reply_markup=get_standard_keyboard(query.from_user.id))


async def enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    update_language(update.callback_query.from_user)

    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(_("Let us start!  What do you do?\n"
                                     "\n"
                                     "Please give a short and simple answer, like \"Teach how to surf\" or \"Help with "
                                     "the immigrations\"."))

    return TYPING_OCCUPATION


async def received_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    update_language(update.message.from_user)

    user_data = context.user_data
    user_data['occupation'] = update.message.text

    await update.message.reply_text(_("Where are you based?\n"
                                      "\n"
                                      "Just the name of the place is enough, like \"A Coruña\""))

    return TYPING_LOCATION


async def received_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the legality"""

    update_language(update.message.from_user)

    user_data = context.user_data
    user_data['location'] = update.message.text

    await update.message.reply_text(_("Finally, please confirm that what you do is legal and does not violate any "
                                      "laws or local regulations.\n"
                                      "\n"
                                      "Is your service legal?"), reply_markup=get_yesno_keyboard())

    return CONFIRMING_LEGALITY


async def confirm_legality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Complete the enrollment"""

    query = update.callback_query

    update_language(query.from_user)

    await query.answer()

    user_data = context.user_data

    if query.data == RESPONSE_YES:
        with LogTime("INSERT OR REPLACE INTO people"):
            global db_connection
            c = db_connection.cursor()

            from_user = query.from_user
            c.execute("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, location) VALUES(?, ?, ?, ?)",
                      (from_user.id, from_user.username, user_data["occupation"], user_data["location"]))

            db_connection.commit()

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(_("We are done, you are now registered!"),
                                       reply_markup=get_standard_keyboard(query.from_user.id))
    elif query.data == RESPONSE_NO:
        delete_user_record(query.from_user.id)

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(
            _("I am sorry.  I cannot register services that do not comply with the laws and local regulations."),
            reply_markup=get_standard_keyboard(0, [COMMAND_RETIRE]))

    user_data.clear()

    return ConversationHandler.END


async def retire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the user from the directory"""

    query = update.callback_query

    update_language(query.from_user)

    delete_user_record(query.from_user.id)

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(_("I am sorry to see you go."),
                                   reply_markup=get_standard_keyboard(0, [COMMAND_RETIRE]))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer"""

    if isinstance(update, Update):
        update_language(update.message.from_user)

    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_string = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))

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

    await update.message.reply_text(_("An internal error occurred.  I have notified my administrator about the error.  "
                                      "Please use the buttons below, hopefully it will work."),
                                    reply_markup=get_standard_keyboard(update.message.from_user.id))


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
    conv_handler = ConversationHandler(entry_points=[CallbackQueryHandler(enroll, pattern=COMMAND_ENROLL)],
                                       states={TYPING_OCCUPATION: [MessageHandler(filters.TEXT, received_occupation)],
                                               TYPING_LOCATION: [MessageHandler(filters.TEXT, received_location)],
                                               CONFIRMING_LEGALITY: [CallbackQueryHandler(confirm_legality)]},
                                       fallbacks=[])

    application.add_handler(conv_handler)

    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    db_connection.close()


if __name__ == "__main__":
    main()
