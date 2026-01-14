"""
Tests for state.py
"""

import unittest
from unittest.mock import MagicMock, patch

from common import i18n
from . import state

from .test_util import *


class TestServiceCategory(unittest.TestCase):
    def tearDown(self):
        with patch('features.services.state.people_category_select_all', return_no_categories):
            state.ServiceCategory.load()

    def test_get(self):
        trans = i18n.default()

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))

        with self.assertRaises(KeyError):
            _category = state.ServiceCategory.get(CATEGORY_1_ID)

        with patch('features.services.state.people_category_select_all', return_single_category):
            state.ServiceCategory.load()

            self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))
            self.assertEqual(state.ServiceCategory.get(CATEGORY_1_ID).title, CATEGORY_1_TITLE)

    def test_load(self):
        with patch('features.services.state.people_category_select_all', return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})

        with patch('features.services.state.people_category_select_all', return_single_category):
            state.ServiceCategory.load()
            self.assertEqual(len(state.ServiceCategory._categories), 1)

        with patch('features.services.state.people_category_select_all', return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})


class TestService(unittest.TestCase):
    def setUp(self):
        with patch('features.services.state.people_category_select_all', return_single_category):
            state.ServiceCategory.load()

    def tearDown(self):
        with patch('features.services.state.people_category_select_all', return_no_categories):
            state.ServiceCategory.load()

    def test_get(self):
        with patch('features.services.state._service_get', service_get):
            service = state.Service.get(SERVICE_101_CATEGORY_ID, SERVICE_101_TG_ID)

            self.assertEqual(service.category.id, CATEGORY_1_ID)
            self.assertEqual(service.category.title, CATEGORY_1_TITLE)
            self.assertEqual(service.tg_id, SERVICE_101_TG_ID)
            self.assertEqual(service.tg_username, tg_username(SERVICE_101_TG_ID))
            self.assertEqual(service.occupation, occupation(SERVICE_101_TG_ID))
            self.assertEqual(service.description, description(SERVICE_101_TG_ID))
            self.assertEqual(service.location, location(SERVICE_101_TG_ID))
            self.assertEqual(service.is_suspended, is_suspended(SERVICE_101_TG_ID))
            self.assertEqual(service.last_modified, last_modified(SERVICE_101_TG_ID))

    def test_delete(self):
        mock_delete = MagicMock()
        with patch('features.services.state._service_delete', mock_delete):
            state.Service.delete(SERVICE_101_TG_ID, CATEGORY_1_ID)

            mock_delete.assert_called_once_with(SERVICE_101_TG_ID, CATEGORY_1_ID)
