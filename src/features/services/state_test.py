"""
Tests for state.py
"""

import unittest
from unittest.mock import MagicMock

from common import i18n
from . import state
from .test_util import *


class TestServiceCategory(unittest.TestCase):
    def tearDown(self):
        with patch("features.services.state._service_category_select_all", return_no_categories):
            state.ServiceCategory.load()

    def test_get(self):
        trans = i18n.default()

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))

        with self.assertRaises(KeyError):
            _category = state.ServiceCategory.get(CATEGORY_1_ID)

        with patch("features.services.state._service_category_select_all", return_single_category):
            state.ServiceCategory.load()

            self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))
            self.assertEqual(state.ServiceCategory.get(CATEGORY_1_ID).title, CATEGORY_1_TITLE)

    def test_load(self):
        with patch("features.services.state._service_category_select_all", return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})

        with patch("features.services.state._service_category_select_all", return_single_category):
            state.ServiceCategory.load()
            self.assertEqual(len(state.ServiceCategory._categories), 1)

        with patch("features.services.state._service_category_select_all", return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})

    def test_all(self):
        # Two-digit IDs would not work.
        unordered_sequence = (4, 9, 3, 2, 8, 5, 6)

        def return_unordered_categories(*_args, **_kwargs) -> Iterator[dict]:
            for category_id in unordered_sequence:
                yield data_row_for_service_category(category_id)

        with patch("features.services.state._service_category_select_all", return_unordered_categories):
            state.ServiceCategory.load()

        all_categories = [c for c in state.ServiceCategory.all()]
        self.assertEqual(len(all_categories), len(unordered_sequence) + 1)
        self.assertListEqual([c.id for c in all_categories][:-1], sorted(unordered_sequence))
        self.assertEqual(all_categories[-1].id, 0)


class TestService(unittest.TestCase):
    def setUp(self):
        with patch("features.services.state._service_category_select_all", return_single_category):
            state.ServiceCategory.load()

    def tearDown(self):
        with patch("features.services.state._service_category_select_all", return_no_categories):
            state.ServiceCategory.load()

    def test_get(self):
        def return_single_service(category_id: int, tg_id: int) -> Iterator[dict]:
            yield data_row_for_service(tg_id, category_id)

        with patch("features.services.state._service_get", return_single_service):
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

    def test_delete(self):
        mock_delete = MagicMock()
        with patch("features.services.state._service_delete", mock_delete):
            state.Service.delete(SERVICE_101_TG_ID, CATEGORY_1_ID)

            mock_delete.assert_called_once_with(SERVICE_101_TG_ID, CATEGORY_1_ID)
