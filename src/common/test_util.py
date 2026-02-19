"""
Stuff used in tests of all features
"""

from unittest.mock import MagicMock

from telegram import Bot, CallbackQuery, Chat, User

from common.settings import settings


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class MockBot(Bot):
    def __init__(self):
        # TODO: Mock this better so that it would not create a real bot
        super().__init__(settings.BOT_TOKEN)

    @property
    def username(self) -> str:
        return "bot_username"

    @property
    def first_name(self) -> str:
        return "Bot"

    async def get_chat(self, *args, **kwargs):
        return Chat(int(kwargs["chat_id"]) if "chat_id" in kwargs else 1, type=Chat.GROUP, title="Main Chat")


class MockQuery(CallbackQuery):
    def __init__(self, _id: str, from_user: User, chat_instance: str, *args, **kwargs):
        super().__init__(_id, from_user, chat_instance, *args, **kwargs)

        self._edit_message_reply_markup_called = False
        self._edit_message_reply_markup_called_with = None

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_reply_markup(self, reply_markup=None, *args, **kwargs):
        self._edit_message_reply_markup_called = True
        self._edit_message_reply_markup_called_with = reply_markup
