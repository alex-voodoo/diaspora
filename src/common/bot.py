"""
Wrappers for calls to the bot
"""

import datetime

from telegram import ChatPermissions, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes


async def get_chat_member_count(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> int:
    return await context.bot.get_chat_member_count(chat_id)


async def forward_message(context: ContextTypes.DEFAULT_TYPE, from_chat_id: int, to_chat_id: int,
                          message_id: int) -> None:
    await context.bot.forward_message(from_chat_id, to_chat_id, message_id)


async def reply(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None) -> None:
    await update.effective_message.reply_text(text=text, reply_markup=reply_markup)


async def restrict_chat_member(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int,
                               until_date: datetime.datetime) -> None:
    await context.bot.restrict_chat_member(chat_id, user_id, ChatPermissions.no_permissions(), until_date=until_date)


async def send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup = None,
               reply_to_message_id: int = None) -> None:
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup,
                                   reply_to_message_id=reply_to_message_id)


async def send_poll(context: ContextTypes.DEFAULT_TYPE, chat_id: int, question: str,
                    options: tuple[str, ...]) -> Message:
    return await context.bot.send_poll(chat_id, is_anonymous=True, question=question, options=options)


async def stop_poll(context: ContextTypes.DEFAULT_TYPE, chat_id: int, poll_message_tg_id: int) -> None:
    return await context.bot.stop_poll(chat_id, poll_message_tg_id)
