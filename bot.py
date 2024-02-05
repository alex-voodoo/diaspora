#!/usr/bin/env python
# pylint: disable=unused-argument

"""
First, a few callback functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
- Configure BOT_TOKEN and DEVELOPER_CHAT_ID appropriately
- Run this script either locally (for testing) or on the server.  It will poll indefinitely.
- Send /start to the bot to initiate the conversation.
- Press Ctrl-C on the command line or send a signal to the process to stop the bot.
"""

import html
import json
import logging
import sqlite3
import time
import traceback
from sqlite3 import Connection

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters,
                          CallbackQueryHandler, )

from secret import BOT_TOKEN, DEVELOPER_CHAT_ID

# Configure logging
# Set higher logging level for httpx to avoid all GET and POST requests being logged.
logging.basicConfig(format="[%(asctime)s] %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TYPING_OCCUPATION, TYPING_LOCATION = range(2)

DELETE_MESSAGE_TIMEOUT = 60

db_connection : Connection

COMMAND_START, COMMAND_HELP, COMMAND_WHO, COMMAND_ENROLL, COMMAND_RETIRE = ("start", "help", "who", "enroll", "retire")

buttons = {"Who": COMMAND_WHO, "Enroll": COMMAND_ENROLL, "Update": COMMAND_ENROLL, "Retire": COMMAND_RETIRE}
button_who, button_enroll, button_update, button_retire = (
    InlineKeyboardButton(text, callback_data=command) for text, command in buttons.items()
)


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
        await self_destructing_reply(update, context, "Let's talk private!")
        return False
    return True


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and show them the selection of options"""

    if not await talking_private(update, context):
        return

    logger.info("Welcoming user {username} (chat ID {chat_id})".format(
        username=update.message.from_user.username, chat_id=update.message.from_user.id))

    await update.message.reply_text("Hi!  This is the service registry for the chat!  Use the buttons below to browse "
                                    "the directory and to add or remove yourself!",
                                    reply_markup=InlineKeyboardMarkup(((button_who, button_enroll, button_retire), )))


async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current registry"""

    logger.info("Who!")

    query = update.callback_query
    await query.answer()

    user_list = ["Here is the directory:"]

    with LogTime("Reading all people from the DB"):
        global db_connection
        c = db_connection.cursor()

        for row in c.execute("SELECT tg_id, tg_username, occupation, location FROM people"):
            values = {key: value for (key,value) in zip((i[0] for i in c.description), row)}
            user_list.append("@{username} ({location}): {occupation}".format(
                username=values["tg_username"], occupation=values["occupation"], location=values["location"]))

        if len(user_list) == 1:
            user_list = ["Nobody has enrolled so far :-( ."]

    await query.edit_message_text(text="\n".join(user_list),
                                  reply_markup=InlineKeyboardMarkup(((button_enroll, button_retire), )))


async def enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    logger.info("Enroll!")

    query = update.callback_query
    await query.answer()

    await query.edit_message_text("Enrolling!  Let us begin with the most important question: What do you do?  "
                                    "Please give a short and simple answer, like \"Teach how to surf\" or \"Help with "
                                    "the immigrations\".")

    return TYPING_OCCUPATION


async def received_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    user_data = context.user_data
    user_data['occupation'] = update.message.text

    await update.message.reply_text("Cool!  Now please tell me where are you based.  "
                                    "Just the name of the place, like \"A Coruña\"")

    return TYPING_LOCATION


async def received_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    user_data = context.user_data
    user_data['location'] = update.message.text

    with LogTime("Updating personal data in the DB"):
        global db_connection
        c = db_connection.cursor()

        from_user = update.message.from_user
        c.execute("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, location) VALUES(?, ?, ?, ?)",
                  (from_user.id, from_user.username, user_data["occupation"], user_data["location"]))

        db_connection.commit()

    user_data.clear()

    await update.message.reply_text("We are done, you are now in the registry!",
                                    reply_markup=InlineKeyboardMarkup(((button_who, button_enroll, button_retire), )))

    return ConversationHandler.END


async def retire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the user from the directory"""

    logger.info("Retire!")

    with LogTime("Deleting personal data from the DB"):
        global db_connection
        c = db_connection.cursor()

        from_user = update.callback_query.from_user
        c.execute("DELETE FROM people WHERE tg_id=?",
                  (from_user.id,))

        db_connection.commit()


    query = update.callback_query
    await query.answer()

    await query.edit_message_text("I am sorry to see you go.",
                                  reply_markup=InlineKeyboardMarkup(((button_who, button_enroll), )))


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the help message"""

    if update.effective_message.chat_id != update.message.from_user.id:
        await self_destructing_reply(update, context,
                                     "Hi!  I keep records on users who would like to offer something to others, "
                                     "and provide that information to everyone in this chat.\n"
                                     "\n"
                                     "To see what I can do, start a private conversation with me.\n"
                                     "\n"
                                     "I will delete this message in a minute to keep this chat clean of my messages.")
        return

    await update.message.reply_text("Hi!  I keep records on users of the Viva Galicia chat who would like to offer "
                                    "something to others, and provide that information to everyone in that chat.\n"
                                    "\n"
                                    "Use the buttons below to see the registry, to add yourself or update your data, "
                                    "and to remove your record.\n",
                                    reply_markup=InlineKeyboardMarkup(((button_who, button_enroll, button_retire), )))



async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer"""

    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    error_message = ("An exception was raised while handling an update\n"
                     f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
                     "</pre>\n\n"
                     f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
                     f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
                     f"<pre>{html.escape(tb_string)}</pre>")

    # Finally, send the message
    await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=error_message, parse_mode=ParseMode.HTML)

    if not await talking_private(update, context):
        return

    await update.message.reply_text("It seems like I screwed up.  Please use the commands below.",
                                    reply_markup=InlineKeyboardMarkup(((button_who, button_enroll, button_retire), )))


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
                                               TYPING_LOCATION: [MessageHandler(filters.TEXT, received_location)], },
                                       fallbacks=[], )

    application.add_handler(conv_handler)

    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    db_connection.close()

if __name__ == "__main__":
    main()
