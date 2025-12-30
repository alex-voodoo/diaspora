"""
Tests for the core part of the Services feature
"""

import datetime
import unittest
from unittest.mock import MagicMock

from telegram import Update, Message, Chat, Bot
from telegram.ext import Application, CallbackContext

from common import i18n
from common.settings import settings

from . import core


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class MockBot(Bot):
    def __init__(self, token: str):
        super().__init__(token)

        self._sent_message = ""

    async def send_message(self, *args, **kwargs):
        self._sent_message = kwargs["text"]


class TestCore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.application.bot = MockBot(token=settings.BOT_TOKEN)

    # def test__format_hint

    def test__maybe_append_limit_warning(self):
        trans = i18n.default()
        initial_message = ["hello", "world"]
        message = initial_message.copy()
        core._maybe_append_limit_warning(trans, message, 0)
        self.assertListEqual(message, initial_message)

        for limit in range(1, 100):
            message = initial_message.copy()
            core._maybe_append_limit_warning(trans, message, limit)
            self.assertListEqual(message[:-1], initial_message)
            self.assertEqual(message[-1], trans.ngettext("SERVICES_DM_DATA_FIELD_LIMIT_S {limit}",
                                                         "SERVICES_DM_DATA_FIELD_LIMIT_P {limit}",
                                                         limit).format(limit=limit))

    async def test__verify_limit_then_retry_or_proceed(self):
        trans = i18n.default()

        current_stage_id = 1
        current_limit = 10
        current_data_field_key = "current"
        next_stage_id = 2
        next_limit = 20
        next_data_field_key = "next"

        next_data_field_insert_text = trans.gettext("SERVICES_DM_ENROLL_ASK_DESCRIPTION")
        next_data_field_update_text = trans.gettext("SERVICES_DM_UPDATE_DESCRIPTION {title} {current_value}")

        current_text = "hello"
        new_current_text_long = "01234567890123456789"

        message = Message(message_id=1, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE),
                          text=new_current_text_long)
        message.set_bot(self.application.bot)
        update = Update(update_id=1,
                        message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        context.user_data["current"] = current_text

        request_next_data_field = AsyncMock()

        result = await core._verify_limit_then_retry_or_proceed(update, context, current_stage_id, current_limit,
                                                                current_data_field_key, next_stage_id,
                                                                next_limit, next_data_field_key,
                                                                next_data_field_insert_text,
                                                                next_data_field_update_text,
                                                                request_next_data_field)
        self.assertEqual(result, current_stage_id)
        self.assertEqual(self.application.bot._sent_message,
                         trans.ngettext("SERVICES_DM_TEXT_TOO_LONG_S {limit} {text}",
                                        "SERVICES_DM_TEXT_TOO_LONG_P {limit} {text}",
                                        current_limit).format(limit=current_limit,
                                                              text=core._format_hint(new_current_text_long,
                                                                                     current_limit)))
        request_next_data_field.assert_not_called()
        request_next_data_field.reset_mock()

        new_current_text_short = "world"
        message = Message(message_id=2, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE),
                          text=new_current_text_short)
        message.set_bot(self.application.bot)
        update = Update(update_id=2,
                        message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        context.user_data["current"] = current_text

        result = await core._verify_limit_then_retry_or_proceed(update, context, current_stage_id, current_limit,
                                                                current_data_field_key, next_stage_id,
                                                                next_limit, next_data_field_key,
                                                                next_data_field_insert_text,
                                                                next_data_field_update_text,
                                                                request_next_data_field)
        self.assertEqual(result, next_stage_id)

        request_next_data_field.assert_called_once_with(update, context, next_limit, next_data_field_key,
                                                        next_data_field_insert_text,
                                                        next_data_field_update_text)
        request_next_data_field.reset_mock()

    # async def _request_next_data_field
    # async def show_main_status
    # noinspection PyUnusedLocal
    # async def _moderate_new_data
    # def _who_people_to_message
    # async def _who_request_category
    # async def _who_received_category
    # async def _who
    # async def _handle_command_enroll
    # async def _handle_command_update
    # async def _accept_category_and_request_occupation
    # async def _verify_occupation_and_request_description
    # async def _verify_description_and_request_location
    # async def _verify_location_and_request_legality
    # async def _verify_legality_and_finalise_data_collection
    # async def _confirm_user_data
    # async def _handle_command_retire
    # async def _retire_received_category
    # async def _abort_conversation
    # async def handle_extended_start_command
    # def init(application: Application, group: int)
