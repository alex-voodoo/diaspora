"""
Tests for the core.py
"""

import unittest
from unittest.mock import call, MagicMock

from telegram import Bot, CallbackQuery, Chat, Message, Update
from telegram.ext import Application, CallbackContext, ConversationHandler

from common import i18n
from . import const, core, keyboards
from .test_util import *


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class MockBot(Bot):
    def __init__(self, token: str):
        super().__init__(token)

    @property
    def username(self) -> str:
        return "bot_username"

    @property
    def first_name(self) -> str:
        return "Bot"

    async def get_chat(self, *args, **kwargs):
        return Chat(1, type=Chat.GROUP, title="Main Chat")


class MockQuery(CallbackQuery):
    def __init__(self, _id: str, from_user: User, chat_instance: str, *args, **kwargs):
        super().__init__(_id, from_user, chat_instance, *args, **kwargs)

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_reply_markup(self, *args, **kwargs):
        pass


class TestCore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.application.bot = MockBot(token=settings.BOT_TOKEN)

    def tearDown(self):
        load_test_categories(0)

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

        with patch("features.services.core.reply") as mock_reply:
            # noinspection PyTypeChecker
            result = await core._verify_limit_then_retry_or_proceed(update, context, current_stage_id, current_limit,
                                                                    current_data_field_key, next_stage_id, next_limit,
                                                                    next_data_field_key, next_data_field_insert_text,
                                                                    next_data_field_update_text,
                                                                    request_next_data_field)
            self.assertEqual(result, current_stage_id)
            mock_reply.assert_called_once_with(update, trans.ngettext("SERVICES_DM_TEXT_TOO_LONG_S {limit} {text}",
                                                                      "SERVICES_DM_TEXT_TOO_LONG_P {limit} {text}",
                                                                      current_limit).format(limit=current_limit,
                                                                                            text=core._format_hint(
                                                                                                new_current_text_long,
                                                                                                current_limit)))
            request_next_data_field.assert_not_called()

        request_next_data_field.reset_mock()

        new_current_text_short = "world"
        message = Message(message_id=2, date=datetime.datetime.now(), chat=Chat(id=1, type=Chat.PRIVATE),
                          text=new_current_text_short)
        message.set_bot(self.application.bot)
        update = Update(update_id=2, message=message)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        context.user_data["current"] = current_text

        with patch("features.services.core.reply") as mock_reply:
            # noinspection PyTypeChecker
            result = await core._verify_limit_then_retry_or_proceed(update, context, current_stage_id, current_limit,
                                                                    current_data_field_key, next_stage_id, next_limit,
                                                                    next_data_field_key, next_data_field_insert_text,
                                                                    next_data_field_update_text,
                                                                    request_next_data_field)
            self.assertEqual(result, next_stage_id)

            mock_reply.assert_not_called()
            request_next_data_field.assert_called_once_with(update, context, next_limit, next_data_field_key,
                                                            next_data_field_insert_text, next_data_field_update_text)

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

        with patch("features.services.core.reply") as mock_reply:
            await core._request_next_data_field(update, context, next_limit, next_data_field_key,
                                                next_data_field_insert_text, next_data_field_update_text)

            expected_reply = [next_data_field_insert_text, ]
            core._maybe_append_limit_warning(trans, expected_reply, next_limit)

            mock_reply.assert_called_once_with(update, "\n".join(expected_reply))

        context.user_data["mode"] = "update"
        context.user_data["category_title"] = category_title

        with patch("features.services.core.reply") as mock_reply:
            await core._request_next_data_field(update, context, next_limit, next_data_field_key,
                                                next_data_field_insert_text, next_data_field_update_text)

            expected_reply = [
                next_data_field_update_text.format(title=category_title, current_value=current_next_text), ]
            core._maybe_append_limit_warning(trans, expected_reply, next_limit)
            mock_reply.assert_called_once_with(update, "\n".join(expected_reply))

    async def test_show_main_status(self):
        def return_no_records(_where_clause: str = "", _where_params: tuple = ()):
            return []

        def return_single_record(_where_clause: str = "", _where_params: tuple = ()):
            return [data_row_for_service(1, 1)]

        def return_multiple_records(_where_clause: str = "", _where_params: tuple = ()):
            return [data_row_for_service(1, 1), data_row_for_service(1, 2)]

        load_test_categories(2)

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

        def return_no_categories(*_args, **_kwargs) -> Iterator[dict]:
            yield from ()

        def return_single_category(*_args, **_kwargs) -> Iterator[dict]:
            yield data_row_for_service_category(1)

        with patch("features.services.core.reply") as mock_reply:
            with patch("features.services.state._service_select", return_no_records):
                with patch("features.services.state._service_category_select_all", return_no_categories):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_no_categories, keyboards.standard(user))
                    mock_reply.reset_mock()

                with patch("features.services.state._service_category_select_all", return_single_category):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_no_categories, keyboards.standard(user))
                    mock_reply.reset_mock()

            with patch("features.services.state._service_select", return_single_record):
                with patch("features.services.state._service_category_select_all", return_no_categories):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_single_record, keyboards.standard(user))
                    mock_reply.reset_mock()

                with patch("features.services.state._service_category_select_all", return_single_category):
                    await core.show_main_status(update, context)
                    mock_reply.assert_called_once_with(update, expected_text_single_record, keyboards.standard(user))
                    mock_reply.reset_mock()

            with patch("features.services.state._service_select", return_multiple_records):
                with patch("features.services.state._service_category_select_all", return_single_category):
                    await core.show_main_status(update, context)
                    records = return_multiple_records()
                    expected_text = [trans.ngettext("SERVICES_DM_HELLO_AGAIN_S {user_first_name} {record_count}",
                                                    "SERVICES_DM_HELLO_AGAIN_P {user_first_name} {record_count}",
                                                    len(records)).format(user_first_name=user.first_name,
                                                                         record_count=len(records))]
                    for record in records:
                        expected_text.append(core._main_status_record_description(state.Service(**record)))
                    mock_reply.assert_called_once_with(update, "\n".join(expected_text), keyboards.standard(user))
                    mock_reply.reset_mock()

    async def test__moderate_new_data(self):
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)

        data = {"category_id": 4, "category_title": "Category title", "description": "Description",
                "location": "Location", "occupation": "Occupation", "tg_id": 1, "tg_username": "username_1"}

        with patch("features.services.core.send") as mock_send:
            with patch("features.services.core.settings") as mock_settings:
                mock_settings.DEVELOPER_CHAT_ID = 12345
                mock_settings.ADMINISTRATORS = []

                await core._moderate_new_data(context, data)

                mock_send.assert_called_once_with(context, mock_settings.DEVELOPER_CHAT_ID, i18n.default().gettext(
                    "SERVICES_ADMIN_APPROVE_USER_DATA {category} {description} {location} {occupation} {"
                    "username}").format(category=data["category_title"], description=data["description"],
                                        location=data["location"], occupation=data["occupation"],
                                        username=data["tg_username"]), keyboards.approve_service_change(data))

                mock_send.reset_mock()

                mock_settings.ADMINISTRATORS = [{"id": 234, "username": "username_234"},
                                                {"id": 567, "username": "username_567"},
                                                {"id": 890, "username": "username_890"}]

                await core._moderate_new_data(context, data)

                calls = [call(context, a["id"], i18n.default().gettext(
                    "SERVICES_ADMIN_APPROVE_USER_DATA {category} {description} {location} {occupation} {"
                    "username}").format(category=data["category_title"], description=data["description"],
                                        location=data["location"], occupation=data["occupation"],
                                        username=data["tg_username"]), keyboards.approve_service_change(data)) for a in
                         mock_settings.ADMINISTRATORS]

                mock_send.assert_has_calls(calls, True)

    async def test__who_request_category(self):
        trans = i18n.default()

        chat = Chat(id=1, type=Chat.PRIVATE)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)

        # Create a query from a user that does not have a username.
        user = User(id=1, first_name="Joe", is_bot=False)
        message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user)
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message, callback_query=MockQuery("1", user, "1", message))

        # _who_request_category() must not be called with an empty set of people.
        with self.assertRaises(RuntimeError):
            await core._who_request_category(update, context, {})

        async def test_with_services_in_categories(category_ids: list[int]):
            with patch("features.services.core.reply") as mock_reply:
                categorised_people = {category_id: [state.Service(**data_row_for_service(1, category_id)),
                                                    state.Service(**data_row_for_service(2, category_id)),
                                                    state.Service(**data_row_for_service(3, category_id))] for
                                      category_id in category_ids}

                expected_category_list = []
                for category in state.ServiceCategory.all():
                    if category.id not in category_ids:
                        continue
                    expected_category_list.append(
                        {"object": category, "text": f"{category.title}: {len(categorised_people[category.id])}"})

                result = await core._who_request_category(update, context, categorised_people)
                self.assertEqual(result, const.SELECTING_CATEGORY)
                mock_reply.assert_called_once_with(update,
                                                   trans.gettext("SERVICES_DM_WHO_CATEGORY_LIST {disclaimer}").format(
                                                       disclaimer=trans.gettext("SERVICES_DM_WHO_DISCLAIMER")),
                                                   keyboards.select_category(
                                                       [c["object"] for c in expected_category_list]))

        await test_with_services_in_categories([0, ])

        load_test_categories(5)

        await test_with_services_in_categories([0, ])
        await test_with_services_in_categories([0, 1])
        await test_with_services_in_categories([0, 2])
        await test_with_services_in_categories([3, 1, 2])
        await test_with_services_in_categories([1, 2, 0, 4, 3, 5])

    async def test__who_received_category(self):
        self.skipTest("Test not implemented")

    async def test__who(self):
        self.skipTest("Test not implemented")

    async def test__handle_command_enroll(self):
        trans = i18n.default()

        chat = Chat(id=1, type=Chat.PRIVATE)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)

        # Create a query from a user that does not have a username.
        user = User(id=1, first_name="Joe", is_bot=False)
        message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user)
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message, callback_query=MockQuery("1", user, "1", message))

        # A user that does not have a username cannot enroll.
        with patch("features.services.core.reply") as mock_reply:
            with patch_service_get_all_by_user_return_nothing():
                result = await core._handle_command_enroll(update, context)

                self.assertEqual(result, ConversationHandler.END)
                mock_reply.assert_called_once_with(update, trans.gettext("SERVICES_DM_ENROLL_USERNAME_REQUIRED"),
                                                   keyboards.standard(user))

        # Create a query from a user that has a username.
        user = User(id=1, first_name="Joe", is_bot=False, username="username_1")
        message = Message(message_id=2, date=datetime.datetime.now(), chat=chat, from_user=user)
        message.set_bot(self.application.bot)
        update = Update(update_id=2, message=message, callback_query=MockQuery("2", user, "1", message))

        with patch("features.services.core.reply") as mock_reply:
            # When no categories are defined, all services are created in the default category.  When the user starts
            # enrolling, they proceed to entering their occupation right away.
            with patch_service_get_all_by_user_return_nothing():
                result = await core._handle_command_enroll(update, context)

                self.assertEqual(result, const.TYPING_OCCUPATION)
                self.assertEqual(context.user_data["category_id"], 0)

                mock_reply.assert_has_calls((call(update, trans.gettext("SERVICES_DM_ENROLL_START")),
                                             call(update, trans.gettext("SERVICES_DM_ENROLL_ASK_OCCUPATION"))), False)

            mock_reply.reset_mock()

            # Load two real categories.
            load_test_categories(2)

            # With some categories defined, the enrollment starts with selecting a category.
            with patch_service_get_all_by_user_return_nothing():
                result = await core._handle_command_enroll(update, context)

                self.assertEqual(result, const.SELECTING_CATEGORY)

                mock_reply.assert_has_calls((call(update, trans.gettext("SERVICES_DM_ENROLL_START")),
                                             call(update, trans.gettext("SERVICES_DM_ENROLL_ASK_CATEGORY"),
                                                  keyboards.select_category())), False)

    async def test__handle_command_update(self):
        self.skipTest("Test not implemented")

    async def test__accept_category_and_request_occupation(self):
        self.skipTest("Test not implemented")

    async def test__verify_occupation_and_request_description(self):
        self.skipTest("Test not implemented")

    async def test__verify_description_and_request_location(self):
        self.skipTest("Test not implemented")

    async def test__verify_location_and_request_legality(self):
        self.skipTest("Test not implemented")

    async def test__verify_legality_and_finalise_data_collection(self):
        self.skipTest(f"Test not implemented")

    async def test__confirm_user_data(self):
        self.skipTest("Test not implemented")

    async def test__handle_command_retire(self):
        self.skipTest("Test not implemented")

    async def test__retire_received_category(self):
        self.skipTest("Test not implemented")

    async def test__abort_conversation(self):
        trans = i18n.default()

        chat = Chat(id=1, type=Chat.PRIVATE)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        user = User(id=1, first_name="Joe", is_bot=False)
        message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user)
        update = Update(update_id=1, message=message)

        with patch("features.services.core.show_main_status") as mock_show_main_status:
            context.user_data["hello"] = "world"
            context.user_data["mode"] = "update"
            context.user_data["other"] = "stuff"

            result = await core._abort_conversation(update, context)

            mock_show_main_status.assert_called_once_with(update, context,
                                                          trans.gettext("SERVICES_DM_CONVERSATION_CANCELLED"))

            self.assertEqual(result, ConversationHandler.END)
            self.assertFalse(bool(context.user_data))

    async def test_handle_extended_start_command(self):
        trans = i18n.default()

        chat = Chat(id=1, type=Chat.PRIVATE)
        context = CallbackContext(application=self.application, chat_id=1, user_id=1)
        user_1 = User(id=1, first_name="Joe", is_bot=False)
        user_2 = User(id=2, first_name="Rob", is_bot=False)
        service = state.Service(**data_row_for_service(1, 1))
        suspended_service = state.Service(**data_row_for_service(2, 1))

        # Load two real categories.
        load_test_categories(2)

        def return_single_service(category_id: int, tg_id: int = 0, tg_username: str = "") -> Iterator[dict]:
            self.assertEqual(tg_id, 0)
            tg_id = test_username_to_tg_id(tg_username)
            yield data_row_for_service(tg_id, category_id)

        def return_no_service(category_id: int, tg_id: int = 0, tg_username: str = "") -> Iterator[dict]:
            yield from ()

        state.Service.set_bot_username("bot_username")

        # Create a message that does not have valid text.
        message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user_1, text="hello")
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message)

        with patch("features.services.core.reply") as mock_reply:
            with self.assertRaises(RuntimeError):
                await core.handle_extended_start_command(update, context)

            mock_reply.assert_not_called()

        message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user_1,
                          text=f"/start service_info_{service.category.id}_{service.tg_username}")
        message.set_bot(self.application.bot)
        update = Update(update_id=1, message=message)

        with patch("features.services.state.people_views_register") as mock_stat:
            with patch("features.services.state._service_get", return_single_service):
                with patch("features.services.core.reply") as mock_reply:
                    await core.handle_extended_start_command(update, context)

                    mock_reply.assert_called_once_with(update, trans.gettext(
                        "SERVICES_DM_YOUR_SERVICE_INFO {category_title} {description} {location} {occupation}").format(
                        category_title=service.category.title, description=service.description,
                        location=service.location, occupation=service.occupation))
                    mock_stat.assert_called_once_with(user_1.id, service.tg_id, service.category.id)

                mock_stat.reset_mock()

                message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user_2,
                                  text=f"/start service_info_{service.category.id}_{service.tg_username}")
                message.set_bot(self.application.bot)
                update = Update(update_id=1, message=message)

                with patch("features.services.core.reply") as mock_reply:
                    await core.handle_extended_start_command(update, context)

                    mock_reply.assert_called_once_with(update, trans.gettext(
                        "SERVICES_DM_SERVICE_INFO {category_title} {description} {location} {occupation} {"
                        "username}").format(category_title=service.category.title, description=service.description,
                                            location=service.location, occupation=service.occupation,
                                            username=service.tg_username))
                    mock_stat.assert_called_once_with(user_2.id, service.tg_id, service.category.id)

                mock_stat.reset_mock()

                message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user_1,
                                  text=f"/start service_info_{suspended_service.category.id}_"
                                       f"{suspended_service.tg_username}")
                message.set_bot(self.application.bot)
                update = Update(update_id=1, message=message)

                with patch("features.services.core.reply") as mock_reply:
                    await core.handle_extended_start_command(update, context)

                    mock_reply.assert_called_once_with(update, trans.gettext("SERVICES_DM_SERVICE_NOT_FOUND"))
                    mock_stat.assert_not_called()

                mock_stat.reset_mock()

                message = Message(message_id=1, date=datetime.datetime.now(), chat=chat, from_user=user_2,
                                  text=f"/start service_info_{suspended_service.category
                                  .id}_{suspended_service.tg_username}")
                message.set_bot(self.application.bot)
                update = Update(update_id=1, message=message)

                with patch("features.services.core.reply") as mock_reply:
                    await core.handle_extended_start_command(update, context)

                    mock_reply.assert_called_once_with(update, trans.gettext(
                        "SERVICES_DM_YOUR_SERVICE_INFO {category_title} {description} {location} {occupation}").format(
                        category_title=suspended_service.category.title, description=suspended_service.description,
                        location=suspended_service.location, occupation=suspended_service.occupation,
                        username=suspended_service.tg_username))
                    mock_stat.assert_called_once_with(user_2.id, suspended_service.tg_id, suspended_service.category.id)

                mock_stat.reset_mock()

            with patch("features.services.state._service_get", return_no_service):
                with patch("features.services.core.reply") as mock_reply:
                    await core.handle_extended_start_command(update, context)

                    mock_reply.assert_called_once_with(update, trans.gettext("SERVICES_DM_SERVICE_NOT_FOUND"))
                    mock_stat.assert_not_called()
