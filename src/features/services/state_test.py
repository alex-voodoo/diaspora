"""
Tests for state.py
"""

import unittest

from common import i18n
from .test_util import *

CATEGORY_1_ID = 1
CATEGORY_1_TITLE = "Category 1"

SERVICE_101_TG_ID = 101
SERVICE_101_CATEGORY_ID = CATEGORY_1_ID


class TestProvider(unittest.TestCase):
    def setUp(self):
        load_test_providers([])

    def tearDown(self):
        load_test_providers([])

    @staticmethod
    def _tg_username_from_tg_id(tg_id: int) -> str:
        return f"username_{tg_id}"

    @staticmethod
    def _next_ping_from_tg_id(tg_id: int) -> datetime.datetime:
        return util.rounded_now() + datetime.timedelta(minutes=tg_id)

    def test_get(self):
        tg_id = 1273
        tg_username = TestProvider._tg_username_from_tg_id(tg_id)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_id(tg_id)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_username(tg_username)

        load_test_providers([tg_id])

        provider_via_tg_id = state.Provider.get_by_tg_id(tg_id)
        self.assertEqual(provider_via_tg_id.tg_id, tg_id)
        self.assertEqual(provider_via_tg_id.tg_username, tg_username)
        self.assertEqual(provider_via_tg_id.next_ping, TestProvider._next_ping_from_tg_id(tg_id))

        provider_via_tg_username = state.Provider.get_by_tg_username(tg_username)

        self.assertIs(provider_via_tg_id, provider_via_tg_username)

    @patch("features.services.state.db.sql_exec")
    def test_create_or_update(self, mock_sql_exec):
        tg_id = 1273

        load_test_providers([tg_id])

        provider_1273 = state.Provider.get_by_tg_id(tg_id)

        new_tg_username = "1273_username"
        new_next_ping = util.rounded_now() + datetime.timedelta(days=50)

        state.Provider.create_or_update(tg_id, new_tg_username, new_next_ping, 3)

        mock_sql_exec.assert_called_once()

        self.assertEqual(provider_1273.tg_username, new_tg_username)
        self.assertEqual(provider_1273.next_ping, new_next_ping)

        mock_sql_exec.reset_mock()

        other_new_tg_id = 21257
        other_new_tg_username = "username_21257"
        other_new_next_ping = util.rounded_now() + datetime.timedelta(days=20)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_id(other_new_tg_id)

        state.Provider.create_or_update(other_new_tg_id, other_new_tg_username, other_new_next_ping, 3)

        mock_sql_exec.assert_called_once()

        state.Provider.get_by_tg_id(other_new_tg_id)

    @patch("features.services.state.db.sql_exec")
    def test_delete(self, mock_sql_exec):
        tg_id = 1273

        load_test_providers([tg_id])

        state.Provider.get_by_tg_id(tg_id)

        state.Provider.delete(tg_id)

        mock_sql_exec.assert_called_once()

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_id(tg_id)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_username(TestProvider._tg_username_from_tg_id(tg_id))


class TestServiceCategory(unittest.TestCase):
    def tearDown(self):
        load_test_categories(0)

    def test_get(self):
        trans = i18n.default()

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))

        with self.assertRaises(KeyError):
            _category = state.ServiceCategory.get(CATEGORY_1_ID)

        load_test_categories(1)

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))
        self.assertEqual(state.ServiceCategory.get(CATEGORY_1_ID).title, CATEGORY_1_TITLE)

    def test_load(self):
        load_test_categories(0)
        self.assertEqual(state.ServiceCategory._categories, {})

        load_test_categories(1)
        self.assertEqual(len(state.ServiceCategory._categories), 1)

        load_test_categories(0)
        self.assertEqual(state.ServiceCategory._categories, {})

    def test_all(self):
        # Two-digit IDs would not work.
        unordered_sequence = (4, 9, 3, 2, 8, 5, 6)

        def return_unordered_categories(*_args, **_kwargs) -> Iterator[dict]:
            for category_id in unordered_sequence:
                yield data_row_for_service_category(category_id)

        with patch("features.services.state.ServiceCategory._do_select_all_query", return_unordered_categories):
            state.ServiceCategory.load()

        all_categories = [c for c in state.ServiceCategory.all()]
        self.assertEqual(len(all_categories), len(unordered_sequence) + 1)
        self.assertListEqual([c.id for c in all_categories][:-1], sorted(unordered_sequence))
        self.assertEqual(all_categories[-1].id, 0)


class TestService(unittest.TestCase):
    def setUp(self):
        load_test_categories(1)

    def tearDown(self):
        load_test_categories(0)

    def test_get(self):
        def return_no_service(_query: str, _parameters: tuple[int, int]) -> Iterator[dict]:
            yield from ()

        with patch("features.services.state.Service._do_select_query", return_no_service):
            with self.assertRaises(state.Service.NotFound):
                state.Service.get(1, 1)

        def return_single_service(_query: str, parameters: tuple[int, int]) -> Iterator[dict]:
            yield data_row_for_service(*parameters)

        with patch("features.services.state.Service._do_select_query", return_single_service):
            service = state.Service.get(SERVICE_101_TG_ID, SERVICE_101_CATEGORY_ID)

            self.assertEqual(service.category.id, CATEGORY_1_ID)
            self.assertEqual(service.category.title, CATEGORY_1_TITLE)
            self.assertEqual(service.tg_id, SERVICE_101_TG_ID)
            self.assertEqual(service.occupation, test_occupation(SERVICE_101_TG_ID))
            self.assertEqual(service.description, test_description(SERVICE_101_TG_ID))
            self.assertEqual(service.location, test_location(SERVICE_101_TG_ID))
            self.assertEqual(service.is_suspended, test_is_suspended(SERVICE_101_TG_ID))
            self.assertEqual(service.last_modified, test_last_modified(SERVICE_101_TG_ID))
