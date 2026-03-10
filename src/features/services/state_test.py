"""
Tests for state.py
"""

import unittest

from common import i18n
from .test_util import *


class TestProvider(unittest.TestCase):
    def setUp(self):
        load_test_providers([])

    def tearDown(self):
        load_test_providers([])

    @staticmethod
    def _next_ping_from_tg_id(tg_id: int) -> datetime.datetime:
        return util.rounded_now() + datetime.timedelta(minutes=tg_id)

    @patch("features.services.state.db.sql_exec")
    def test_tg_username_setter(self, mock_sql_exec):
        tg_id = 1234
        original_tg_username = test_tg_username(tg_id)

        load_test_providers([tg_id])

        provider = state.Provider.get_by_tg_id(tg_id)

        with self.assertRaises(AssertionError):
            provider.tg_username = ""
        self.assertEqual(provider.tg_username, original_tg_username)
        mock_sql_exec.assert_not_called()

        with self.assertRaises(AssertionError):
            provider.tg_username = "   "
        self.assertEqual(provider.tg_username, original_tg_username)
        mock_sql_exec.assert_not_called()

        provider.tg_username = f"   {original_tg_username}   "
        self.assertEqual(provider.tg_username, original_tg_username)
        mock_sql_exec.assert_not_called()

        totally_new_username = "TotallyNewOne"
        provider.tg_username = totally_new_username
        self.assertEqual(provider.tg_username, totally_new_username)

        mock_sql_exec.assert_called_once()
        self.assertEqual(mock_sql_exec.call_args[0][1], (provider.tg_username, provider.tg_id))

    @patch("features.services.state.db.sql_exec")
    def test_ping_management(self, mock_sql_exec):
        tg_id = 12341
        load_test_providers([tg_id])

        provider = state.Provider.get_by_tg_id(tg_id)

        self.assertEqual(provider.remaining_ping_count, settings.SERVICES_PING_ATTEMPT_COUNT)

        while provider.remaining_ping_count > 0:
            current_remaining_ping_count = provider.remaining_ping_count

            provider.consume_ping_attempt_and_schedule_next_attempt()

            self.assertEqual(provider.remaining_ping_count, current_remaining_ping_count - 1)
            self.assertEqual(provider.next_ping, state.Provider.get_next_ping_reminder_date())

            mock_sql_exec.assert_called_once()
            self.assertEqual(mock_sql_exec.call_args[0][1],
                             (util.db_format(provider.next_ping), provider.remaining_ping_count, provider.tg_id))
            mock_sql_exec.reset_mock()

        with self.assertRaises(AssertionError):
            provider.consume_ping_attempt_and_schedule_next_attempt()
        mock_sql_exec.assert_not_called()

        provider.reset_ping_attempts_and_schedule_next_ping()
        self.assertEqual(provider.remaining_ping_count, settings.SERVICES_PING_ATTEMPT_COUNT)
        self.assertEqual(provider.next_ping, state.Provider.get_next_ping_date())

        mock_sql_exec.assert_called_once()
        self.assertEqual(mock_sql_exec.call_args[0][1],
                         (util.db_format(provider.next_ping), provider.remaining_ping_count, provider.tg_id))

    def test_get(self):
        tg_id = 1273
        tg_username = test_tg_username(tg_id)

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
    def test_delete(self, mock_sql_exec):
        tg_id = 1273

        load_test_providers([tg_id])

        state.Provider.get_by_tg_id(tg_id)

        state.Provider.delete(tg_id)

        mock_sql_exec.assert_called_once()
        self.assertEqual(mock_sql_exec.call_args[0][1], (tg_id,))

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_id(tg_id)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_username(test_tg_username(tg_id))


class TestServiceCategory(unittest.TestCase):
    def tearDown(self):
        load_test_categories(0)

    def test_get(self):
        trans = i18n.default()

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))

        category_id = 1

        with self.assertRaises(KeyError):
            state.ServiceCategory.get(category_id)

        load_test_categories(1)

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))
        state.ServiceCategory.get(category_id)

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
            service_id = 123214
            category_id = 1

            service = state.Service.get(service_id, category_id)

            self.assertIs(service.category, state.ServiceCategory.get(category_id))

            self.assertEqual(service.tg_id, service_id)
            self.assertEqual(service.occupation, test_occupation(service_id))
            self.assertEqual(service.description, test_description(service_id))
            self.assertEqual(service.location, test_location(service_id))
            self.assertEqual(service.is_suspended, test_is_suspended(service_id))
            self.assertEqual(service.last_modified, test_last_modified(service_id))
