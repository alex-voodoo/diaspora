"""
Tests for keyboards used in the Services feature
"""

import unittest
from collections.abc import Iterator
from unittest.mock import patch

from telegram import InlineKeyboardButton

from common import i18n
from . import const, keyboards, state
from .test_util import *


class TestKeyboards(unittest.TestCase):
    def tearDown(self):
        with patch('features.services.state._service_category_select_all', return_no_categories):
            state.ServiceCategory.load()

    def test_standard(self):
        user = create_test_user(SERVICE_101_TG_ID)
        trans = i18n.default()

        def return_no_services(_tg_id: int) -> Iterator[dict]:
            for _c in []:
                yield {}

        def return_single_service_default_category(tg_id: int) -> Iterator[dict]:
            yield data_row_for_service(tg_id, 0)

        def return_single_service_category_1(tg_id: int) -> Iterator[dict]:
            yield data_row_for_service(tg_id, CATEGORY_1_ID)

        def return_all_categories_without_default(tg_id: int) -> Iterator[dict]:
            for c in state.ServiceCategory.all():
                yield {"tg_id": tg_id, "tg_username": tg_username(tg_id), "category_id": c.id,
                       "occupation": occupation(tg_id), "description": description(tg_id), "location": location(tg_id),
                       "is_suspended": is_suspended(tg_id), "last_modified": last_modified(tg_id)}

        def return_all_categories_with_default(tg_id: int) -> Iterator[dict]:
            for c in state.ServiceCategory.all():
                yield data_row_for_service(tg_id, c.id)
            yield data_row_for_service(tg_id, 0)

        def assert_who_enroll() -> None:
            keyboard = keyboards.standard(user)
            button_container = keyboard.inline_keyboard
            self.assertEqual(len(button_container), 2)
            self.assertIn(
                (InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_WHO"), callback_data=const.COMMAND_WHO),),
                button_container)
            self.assertIn(
                (InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_ENROLL"), callback_data=const.COMMAND_ENROLL),),
                button_container)

        def assert_who_enroll_more_update_retire() -> None:
            keyboard = keyboards.standard(user)
            button_container = keyboard.inline_keyboard
            self.assertEqual(len(button_container), 3)
            self.assertIn(
                (InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_WHO"), callback_data=const.COMMAND_WHO),),
                button_container)
            self.assertIn((
            InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_ENROLL_MORE"), callback_data=const.COMMAND_ENROLL),),
                button_container)
            self.assertIn((InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_UPDATE"),
                                                callback_data=const.COMMAND_UPDATE),
                           InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_RETIRE"),
                                                callback_data=const.COMMAND_RETIRE)), button_container)

        def assert_who_update_retire() -> None:
            keyboard = keyboards.standard(user)
            button_container = keyboard.inline_keyboard
            self.assertEqual(len(button_container), 2)
            self.assertIn(
                (InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_WHO"), callback_data=const.COMMAND_WHO),),
                button_container)
            self.assertIn((InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_UPDATE"),
                                                callback_data=const.COMMAND_UPDATE),
                           InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_RETIRE"),
                                                callback_data=const.COMMAND_RETIRE)), button_container)

        with patch('features.services.state._service_get_all_by_user', return_no_services):
            assert_who_enroll()

        with patch('features.services.state._service_get_all_by_user', return_single_service_default_category):
            assert_who_update_retire()

        with patch('features.services.state._service_category_select_all', return_two_categories):
            state.ServiceCategory.load()

        with patch('features.services.state._service_get_all_by_user', return_no_services):
            assert_who_enroll()

        with patch('features.services.state._service_get_all_by_user', return_single_service_default_category):
            assert_who_enroll_more_update_retire()

        with patch('features.services.state._service_get_all_by_user', return_single_service_category_1):
            assert_who_enroll_more_update_retire()

        with patch('features.services.state._service_get_all_by_user', return_all_categories_without_default):
            assert_who_enroll_more_update_retire()

        with patch('features.services.state._service_get_all_by_user', return_all_categories_with_default):
            assert_who_update_retire()
