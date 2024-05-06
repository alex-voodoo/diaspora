"""
Functions for checking whether the update meets certain criteria
"""

import logging

from telegram import ChatMember, ChatMemberLeft, ChatMemberBanned, User
from telegram.ext import ContextTypes

from settings import MAIN_CHAT_ID

logger = logging.getLogger(__name__)

async def is_member_of_main_chat(user: User, context: ContextTypes.DEFAULT_TYPE) -> bool:
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


