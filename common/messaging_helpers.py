"""
Messaging helpers
"""

import logging

import telegram
from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def safe_delete_message(context: ContextTypes.DEFAULT_TYPE, message_id: int, chat_id: int) -> None:
    """Try to delete a message and log possible exception

    It is quite common situation when a message disappears before the bot tries to delete it.  Trying to proceed results
    in an exception raised, which this function handles (logs the event).
    """

    try:
        await context.bot.delete_message(message_id=message_id, chat_id=chat_id)
    except telegram.error.BadRequest as e:
        logger.warning(e)


async def safe_delete_reaction(message: Message):
    """Try to delete a reaction and log possible exception"""

    try:
        await message.set_reaction([])
    except telegram.error.BadRequest as e:
        logger.warning(e)


async def delete_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete the message contained in the data of the context job

    This function is called with a delay and is intended to delete a message sent by the bot earlier, and also delete
    the message that the former one was sent in reply to.  It is used to clean automatically the messages that users
    send to the bot in the chat: the intended way to use it is communicating via private messages.

    Use `self_destructing_reply()` as a wrapper for this function.
    """

    message_to_delete, delete_reply_to = context.job.data

    await safe_delete_message(context, message_to_delete.message_id, message_to_delete.chat.id)
    if delete_reply_to:
        await safe_delete_message(context, message_to_delete.reply_to_message.message_id, message_to_delete.chat.id)


async def delete_reaction(context: ContextTypes.DEFAULT_TYPE):
    """Delete the reaction that the bot sent earlier to a message identified by data contained in the context job

    Use `self_destructing_reaction()` as a wrapper for this function.
    """

    await safe_delete_reaction(context.job.data)


async def self_destructing_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, message_body: str, timeout: int,
                                 delete_reply_to=True):
    """Replies to the message contained in the `update`.  If `timeout` is greater than zero, schedules the reply to be
    deleted."""

    if update.effective_message.chat_id == update.message.from_user.id:
        logger.error("Cannot delete messages in private chats!")
        return

    posted_message = await update.message.reply_text(message_body, parse_mode=ParseMode.HTML,
                                                     disable_web_page_preview=True)

    if timeout > 0:
        context.job_queue.run_once(delete_message, timeout, data=(posted_message, delete_reply_to))


async def self_destructing_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE, reaction: list, timeout: int):
    """Reacts to a message contained in the `update`.  If `timeout` is greater than zero, schedules the reaction to be
    deleted."""

    await update.effective_message.set_reaction(reaction)

    if timeout > 0:
        context.job_queue.run_once(delete_reaction, timeout, data=update.effective_message)
