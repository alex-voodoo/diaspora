"""
Tests for keyboards.py
"""

import unittest
from collections.abc import Iterable

from telegram import InlineKeyboardButton

from common import i18n
from . import const, keyboards
from .test_util import *


class TestKeyboards(unittest.TestCase):
    def setUp(self):
        load_test_categories(0)

    def tearDown(self):
        load_test_categories(0)

    def test_standard(self):
        user = create_test_user(SERVICE_101_TG_ID)
        trans = i18n.default()

        def return_single_service_default_category(tg_id: int) -> Iterator[dict]:
            yield data_row_for_service(tg_id, 0)

        def return_single_service_category_1(tg_id: int) -> Iterator[dict]:
            yield data_row_for_service(tg_id, CATEGORY_1_ID)

        def return_all_categories_without_default(tg_id: int) -> Iterator[dict]:
            for c in state.ServiceCategory.all(False):
                yield data_row_for_service(tg_id, c.id)

        def return_all_categories_with_default(tg_id: int) -> Iterator[dict]:
            for c in state.ServiceCategory.all(True):
                yield data_row_for_service(tg_id, c.id)

        who_button = InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_WHO"), callback_data=const.COMMAND_WHO)
        enroll_button = InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_ENROLL"),
                                             callback_data=const.COMMAND_ENROLL)
        enroll_more_button = InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_ENROLL_MORE"),
                                                  callback_data=const.COMMAND_ENROLL)
        update_button = InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_UPDATE"),
                                             callback_data=const.COMMAND_UPDATE)
        retire_button = InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_RETIRE"),
                                             callback_data=const.COMMAND_RETIRE)

        def assert_who_enroll() -> None:
            keyboard = keyboards.standard(user)
            button_container = keyboard.inline_keyboard
            self.assertEqual(len(button_container), 2)
            self.assertIn((who_button,), button_container)
            self.assertIn((enroll_button,), button_container)

        def assert_who_enroll_more_update_retire() -> None:
            keyboard = keyboards.standard(user)
            button_container = keyboard.inline_keyboard
            self.assertEqual(len(button_container), 3)
            self.assertIn((who_button,), button_container)
            self.assertIn((enroll_more_button,), button_container)
            self.assertIn((update_button, retire_button), button_container)

        def assert_who_update_retire() -> None:
            keyboard = keyboards.standard(user)
            button_container = keyboard.inline_keyboard
            self.assertEqual(len(button_container), 2)
            self.assertIn((who_button,), button_container)
            self.assertIn((update_button, retire_button), button_container)

        # When no categories are registered, all services belong to the "default" category that does not actually exist.
        # A user can create only a single service, and when they have it, they can either update it or delete.

        with patch_service_get_all_by_user_return_nothing():
            assert_who_enroll()

        with patch("features.services.state._service_get_all_by_user", return_single_service_default_category):
            assert_who_update_retire()

        # Load some real categories.
        load_test_categories(5)

        # When there are real categories, users can register services until they have a service in each category,
        # including the default one.

        with patch_service_get_all_by_user_return_nothing():
            assert_who_enroll()

        with patch("features.services.state._service_get_all_by_user", return_single_service_default_category):
            assert_who_enroll_more_update_retire()

        with patch("features.services.state._service_get_all_by_user", return_single_service_category_1):
            assert_who_enroll_more_update_retire()

        with patch("features.services.state._service_get_all_by_user", return_all_categories_without_default):
            assert_who_enroll_more_update_retire()

        with patch("features.services.state._service_get_all_by_user", return_all_categories_with_default):
            assert_who_update_retire()

    def test_select_category(self):
        trans = i18n.default()

        def test_keyboard(custom_categories: Iterable[state.ServiceCategory], expected_button_ids: list[int]):
            result = keyboards.select_category(custom_categories)

            if len(expected_button_ids) == 0:
                self.assertIsNone(result)
                return

            self.assertSequenceEqual(result.inline_keyboard,
                                     [(InlineKeyboardButton(c.title, callback_data=c.id),) for c in
                                      [state.ServiceCategory.get(category_id) for category_id in expected_button_ids]])

        def category_list(ids: list[int]) -> Iterator[state.ServiceCategory]:
            for category_id in ids:
                yield state.ServiceCategory(**data_row_for_service_category(category_id))

        # When no categories are defined in the DB, the default keyboard should have a single button for the default
        # category.
        keyboard = keyboards.select_category()
        self.assertEqual(len(keyboard.inline_keyboard), 1)
        self.assertIn((InlineKeyboardButton(trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"), callback_data=0),),
                      keyboard.inline_keyboard)

        test_keyboard([], [])
        test_keyboard(category_list([0]), [0])
        test_keyboard(category_list([1, 2, 3, 4]), [])
        test_keyboard(category_list([0, 1, 2, 3, 4]), [0])

        # Load two real categories.
        load_test_categories(2)

        # When some categories are defined in the DB, the default keyboard should have them all, plus the default
        # category.
        keyboard = keyboards.select_category()
        expected_buttons = [(InlineKeyboardButton(c.title, callback_data=c.id),) for c in
                            [state.ServiceCategory.get(category_id) for category_id in [1, 2, 0]]]
        self.assertSequenceEqual(expected_buttons, keyboard.inline_keyboard)

        test_keyboard([], [])
        test_keyboard(category_list([0]), [0])
        test_keyboard(category_list([1, 2, 3, 4]), [1, 2])
        test_keyboard(category_list([0, 1, 2, 3, 4]), [1, 2, 0])
