"""
Tests for state.py
"""

import unittest
from unittest.mock import MagicMock

from common import i18n, util
from .test_util import *

CATEGORY_1_ID = 1
CATEGORY_1_TITLE = "Category 1"

SERVICE_101_TG_ID = 101
SERVICE_101_CATEGORY_ID = CATEGORY_1_ID


class TestProvider(unittest.TestCase):
    def tearDown(self):
        def yield_nothing(_query: str) -> Iterator[dict]:
            yield from ()

        with patch("features.services.state.Provider._do_select_query", yield_nothing):
            state.Provider.load()

    def test_get(self):
        tg_id = 1273
        tg_username = "username_1273"
        next_ping = util.rounded_now() + datetime.timedelta(days=45)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_id(tg_id)

        with self.assertRaises(state.Provider.NotFound):
            state.Provider.get_by_tg_username(tg_username)

        def get_one_provider(_query: str) -> Iterator[dict]:
            yield {"tg_id": tg_id, "tg_username": tg_username, "next_ping": next_ping}

        with patch("features.services.state.Provider._do_select_query", get_one_provider):
            state.Provider.load()

        provider_via_tg_id = state.Provider.get_by_tg_id(tg_id)
        self.assertEqual(provider_via_tg_id.tg_id, tg_id)
        self.assertEqual(provider_via_tg_id.tg_username, tg_username)
        self.assertEqual(provider_via_tg_id.next_ping, next_ping)

        provider_via_tg_username = state.Provider.get_by_tg_username(tg_username)

        self.assertIs(provider_via_tg_id, provider_via_tg_username)


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
            self.assertEqual(service.tg_username, test_tg_username(SERVICE_101_TG_ID))
            self.assertEqual(service.occupation, test_occupation(SERVICE_101_TG_ID))
            self.assertEqual(service.description, test_description(SERVICE_101_TG_ID))
            self.assertEqual(service.location, test_location(SERVICE_101_TG_ID))
            self.assertEqual(service.is_suspended, test_is_suspended(SERVICE_101_TG_ID))
            self.assertEqual(service.last_modified, test_last_modified(SERVICE_101_TG_ID))
