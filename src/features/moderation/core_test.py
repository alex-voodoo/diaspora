import datetime
import unittest
from unittest.mock import patch

from telegram import Message, Chat, Update, MessageReactionUpdated, ReactionType
from telegram.ext import Application

from common import test_util, util
from common.settings import settings
from features.moderation import core


class TestCore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.application.bot = test_util.MockBot()

    @patch("features.moderation.core.settings")
    @patch("features.moderation.state.MainChatMessage.log")
    async def test__maybe_log_message(self, mock_log, mock_settings):
        mock_settings.MAIN_CHAT_ID = 12345
        main_chat = Chat(id=mock_settings.MAIN_CHAT_ID, type=Chat.GROUP)

        # Message from another chat should not be given to this function.
        message = Message(message_id=1, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE), text="Hey")
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message)

        with self.assertRaises(AssertionError):
            core._maybe_log_message(update)
        mock_log.assert_not_called()

        def test_maybe_log_message(update_from_main_chat: Update, should_log: bool):
            core._maybe_log_message(update_from_main_chat)
            if should_log:
                mock_log.assert_called_once_with(update_from_main_chat.effective_message)
                mock_log.reset_mock()
            else:
                mock_log.assert_not_called()

        message = Message(message_id=1, date=datetime.datetime.now(), chat=main_chat, text="Hey")
        message.set_bot(self.application.bot)

        # New message should be logged.
        test_maybe_log_message(Update(update_id=1, message=message), True)
        # Edited message should be logged.
        test_maybe_log_message(Update(update_id=1, edited_message=message), True)
        # Any other update (without message or edited message) should not be logged.
        test_maybe_log_message(Update(update_id=1,
                                      message_reaction=MessageReactionUpdated(main_chat, 1, util.rounded_now(), (),
                                                                              (ReactionType(ReactionType.EMOJI, ),))),
                               False)
