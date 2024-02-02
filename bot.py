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
import traceback

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, )

from secret import BOT_TOKEN, DEVELOPER_CHAT_ID

# Configure logging
# Set higher logging level for httpx to avoid all GET and POST requests being logged.
logging.basicConfig(format="[%(asctime)s] %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TYPING_OCCUPATION, TYPING_LOCATION = range(2)


async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current registry"""

    conn = sqlite3.connect("people.db")
    c = conn.cursor()

    user_list = ["Here is the directory:"]

    for row in c.execute("SELECT tg_id, tg_username, occupation, location FROM people"):
        values = {key: value for (key,value) in zip((i[0] for i in c.description), row)}
        user_list.append("@{username} ({location}): {occupation}".format(
            username=values["tg_username"], occupation=values["occupation"], location=values["location"]))

    conn.close()

    await update.message.reply_text("\n".join(user_list))


async def enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    await update.message.reply_text("Enrolling!  Let us begin with the most important question: What do you do?  "
                                    "Please give a short and simple answer, like \"Teach how to surf\" or \"Help with "
                                    "the immigrations\".", reply_markup=ReplyKeyboardRemove(), )

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

    await update.message.reply_text("So your occupation is: \"{}\", and you are based in {}.  "
                                    "We will store that!".format(user_data["occupation"], user_data["location"]),
                                    reply_markup=hello_markup)

    conn = sqlite3.connect("people.db")
    c = conn.cursor()

    from_user = update.message.from_user
    c.execute("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, location) VALUES(?, ?, ?, ?)",
              (from_user.id, from_user.username, user_data["occupation"], user_data["location"]))

    conn.commit()
    conn.close()

    user_data.clear()

    return ConversationHandler.END


async def retire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the user from the directory"""
    await update.message.reply_text("ONE CANNOT LEAVE!!!!!")


main_commands = {"Who": who, "Enroll": enroll, "Retire": retire}

hello_markup = ReplyKeyboardMarkup([[command, ] for command in main_commands.keys()])


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and show them the selection of options"""

    logger.info("Welcoming user {}".format(update.effective_chat.id))

    await update.message.reply_text("Hi!  This is the service registry for the chat!  Use the buttons below to browse "
                                    "the directory and to add or remove yourself!", reply_markup=hello_markup)


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the message.  If it is a recognised command, execute it.  Otherwise, show help."""

    if update.message.text in main_commands:
        await main_commands[update.message.text](update, context)
        return

    await update.message.reply_text("I could not parse that.  Here are the things that I do understand.",
                                    reply_markup=hello_markup)


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
    await update.message.reply_text("It seems like I screed up.  Please use the commands below.",
                                    reply_markup=hello_markup)


def main() -> None:
    """Run the bot"""

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", hello))

    # Add conversation handler that questions the user about his profile
    conv_handler = ConversationHandler(entry_points=[MessageHandler(filters.Regex("^Enroll$"), enroll)],
                                       states={TYPING_OCCUPATION: [MessageHandler(filters.TEXT, received_occupation)],
                                               TYPING_LOCATION: [MessageHandler(filters.TEXT, received_location)], },
                                       fallbacks=[], )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT, message))

    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
