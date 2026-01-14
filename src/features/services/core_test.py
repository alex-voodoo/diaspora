"""
Tests for the core part of the Services feature
"""

import unittest
from unittest.mock import MagicMock, patch

from telegram import Bot, Chat, Message, Update, User
from telegram.ext import Application, CallbackContext

from common import i18n
from common.settings import settings
from . import core, keyboards, state
from .test_util import *


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class MockBot(Bot):
    def __init__(self, token: str):
        super().__init__(token)

        self._sent_message_text = ""

    async def send_message(self, *args, **kwargs):
        self._sent_message_text = kwargs["text"]

    @property
    def username(self) -> str:
        return "bot_username"

    @property
    def first_name(self) -> str:
        return "Bot"

    async def get_chat(self, *args, **kwargs):
        return Chat(1, type=Chat.GROUP, title="Main Chat")


class TestCore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.application.bot = MockBot(token=settings.BOT_TOKEN)

        with patch('features.services.state._service_category_select_all', return_two_categories):
            state.ServiceCategory.load()

    def tearDown(self):
        with patch('features.services.state._service_category_select_all', return_no_categories):
            state.ServiceCategory.load()

    @property
    def sent_message_text(self) -> str:
        return self.application.bot._sent_message_text

    @sent_message_text.setter
    def sent_message_text(self, value):
        self.application.bot._sent_message_text = value

    # def test__format_hint

    def test__format_deep_link_to_service(self):
        bot_username = "bot_username"
        username = "username"
        self.assertEqual(core._format_deep_link_to_service(bot_username, None, username),
                         f"t.me/{bot_username}?start=service_info_0_{username}")
        self.assertEqual(core._format_deep_link_to_service(bot_username, 0, username),
                         f"t.me/{bot_username}?start=service_info_0_{username}")
        self.assertEqual(core._format_deep_link_to_service(bot_username, 1, username),
                         f"t.me/{bot_username}?start=service_info_1_{username}")

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
                                                         "SERVICES_DM_DATA_FIELD_LIMIT_P {limit}", limit).format(
                limit=limit))

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
        update = Update(update_id=1, message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        context.user_data["current"] = current_text

        request_next_data_field = AsyncMock()

        # noinspection PyTypeChecker
        result = await core._verify_limit_then_retry_or_proceed(update, context, current_stage_id, current_limit,
                                                                current_data_field_key, next_stage_id, next_limit,
                                                                next_data_field_key, next_data_field_insert_text,
                                                                next_data_field_update_text, request_next_data_field)
        self.assertEqual(result, current_stage_id)
        self.assertEqual(self.sent_message_text, trans.ngettext("SERVICES_DM_TEXT_TOO_LONG_S {limit} {text}",
                                                                "SERVICES_DM_TEXT_TOO_LONG_P {limit} {text}",
                                                                current_limit).format(limit=current_limit,
                                                                                      text=core._format_hint(
                                                                                          new_current_text_long,
                                                                                          current_limit)))
        request_next_data_field.assert_not_called()

        request_next_data_field.reset_mock()
        self.sent_message_text = ""

        new_current_text_short = "world"
        message = Message(message_id=2, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE),
                          text=new_current_text_short)
        message.set_bot(self.application.bot)
        update = Update(update_id=2, message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        context.user_data["current"] = current_text

        # noinspection PyTypeChecker
        result = await core._verify_limit_then_retry_or_proceed(update, context, current_stage_id, current_limit,
                                                                current_data_field_key, next_stage_id, next_limit,
                                                                next_data_field_key, next_data_field_insert_text,
                                                                next_data_field_update_text, request_next_data_field)
        self.assertEqual(result, next_stage_id)

        request_next_data_field.assert_called_once_with(update, context, next_limit, next_data_field_key,
                                                        next_data_field_insert_text, next_data_field_update_text)
        self.assertEqual(self.sent_message_text, "")

    async def test__request_next_data_field(self):
        trans = i18n.default()

        next_limit = 20
        next_data_field_key = "next"
        category_title = "Category Title"
        current_next_text = "Current next text"

        next_data_field_insert_text = trans.gettext("SERVICES_DM_ENROLL_ASK_DESCRIPTION")
        next_data_field_update_text = trans.gettext("SERVICES_DM_UPDATE_DESCRIPTION {title} {current_value}")

        message = Message(message_id=1, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE),
                          text="nothing")
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        context.user_data["next"] = current_next_text

        await core._request_next_data_field(update, context, next_limit, next_data_field_key,
                                            next_data_field_insert_text, next_data_field_update_text)

        expected_sent_message_text = [next_data_field_insert_text, ]
        core._maybe_append_limit_warning(trans, expected_sent_message_text, next_limit)
        self.assertEqual(self.sent_message_text, "\n".join(expected_sent_message_text))

        context.user_data["mode"] = "update"
        context.user_data["category_title"] = category_title

        await core._request_next_data_field(update, context, next_limit, next_data_field_key,
                                            next_data_field_insert_text, next_data_field_update_text)

        expected_sent_message_text = [
            next_data_field_update_text.format(title=category_title, current_value=current_next_text), ]
        core._maybe_append_limit_warning(trans, expected_sent_message_text, next_limit)
        self.assertEqual(self.sent_message_text, "\n".join(expected_sent_message_text))

    async def test_show_main_status(self):
        def return_no_records(where_clause: str = "", where_params: tuple = ()):
            return []

        def return_single_record(where_clause: str = "", where_params: tuple = ()):
            return [{"tg_id": 1, "tg_username": "U", "category_id": 1, "occupation": "O", "description": "D",
                     "location": "L", "is_suspended": False, "last_modified": datetime.datetime.now()}]

        def return_multiple_records(where_clause: str = "", where_params: tuple = ()):
            return [{"tg_id": 1, "tg_username": "U", "category_id": 1, "occupation": "O", "description": "D",
                     "location": "L", "is_suspended": False, "last_modified": datetime.datetime.now()},
                    {"tg_id": 1, "tg_username": "U", "category_id": 2, "occupation": "O2", "description": "D2",
                     "location": "L2", "is_suspended": False, "last_modified": datetime.datetime.now()}]

        state.Service.set_bot_username("bot_username")

        user = User(id=1, first_name="Joe", is_bot=False, username="joe_username")
        message = Message(message_id=1, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE),
                          text="nothing", from_user=user)
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        chat = await context.bot.get_chat(1)
        chat_title = chat.title

        trans = i18n.default()
        expected_text_no_categories = trans.gettext("SERVICES_DM_HELLO {bot_first_name} {main_chat_name}").format(
            bot_first_name=context.bot.first_name, main_chat_name=chat_title)
        expected_text_single_record = "\n".join(
            [trans.gettext("SERVICES_DM_HELLO_AGAIN {user_first_name}").format(user_first_name=user.first_name),
             core._main_status_record_description(state.Service(**return_single_record()[0]))])

        with patch('features.services.core.reply') as mock_reply:
            with patch('features.services.state._service_select', return_no_records):
                with patch('features.services.state._service_category_select_all', return_no_categories):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_no_categories, keyboards.standard(user))
                    mock_reply.reset_mock()

                with patch('features.services.state._service_category_select_all', return_single_category):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_no_categories, keyboards.standard(user))
                    mock_reply.reset_mock()

            with patch('features.services.state._service_select', return_single_record):
                with patch('features.services.state._service_category_select_all', return_no_categories):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_single_record, keyboards.standard(user))
                    mock_reply.reset_mock()

                with patch('features.services.state._service_category_select_all', return_single_category):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_single_record, keyboards.standard(user))
                    mock_reply.reset_mock()

            with patch('features.services.state._service_select', return_multiple_records):
                with patch('features.services.state._service_category_select_all', return_single_category):
                    await core.show_main_status(update, context)
                    records = return_multiple_records()
                    expected_text = [trans.ngettext("SERVICES_DM_HELLO_AGAIN_S {user_first_name} {record_count}",
                                                    "SERVICES_DM_HELLO_AGAIN_P {user_first_name} {record_count}",
                                                    len(records)).format(user_first_name=user.first_name,
                                                                         record_count=len(records))]
                    for record in records:
                        expected_text.append(
                            core._main_status_record_description(state.Service(**record)))
                    mock_reply.assert_called_once_with(update, "\n".join(expected_text), keyboards.standard(user))
                    mock_reply.reset_mock()

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

    # def init
