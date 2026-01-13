"""
Tests for state.py
"""

import datetime
import unittest
from unittest.mock import patch

from common import i18n
from . import state

CATEGORY_1_ID = 1
CATEGORY_1_TITLE = "Category 1"
SERVICE_10001_TG_ID = 10001
SERVICE_10001_TG_USERNAME = "username_10001"
SERVICE_10001_LAST_MODIFIED = datetime.datetime.fromisoformat("2000-01-03 13:23:41")


def _return_single_category() -> list:
    return [{"id": CATEGORY_1_ID, "title": CATEGORY_1_TITLE}]


def _return_no_categories() -> list:
    return []


class TestServiceCategory(unittest.TestCase):
    def tearDown(self):
        with patch('features.services.state.people_category_select_all', _return_no_categories):
            state.ServiceCategory.load()

    def test_get(self):
        trans = i18n.default()

        self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))

        with self.assertRaises(KeyError):
            _category = state.ServiceCategory.get(CATEGORY_1_ID)

        with patch('features.services.state.people_category_select_all', _return_single_category):
            state.ServiceCategory.load()

            self.assertEqual(state.ServiceCategory.get(0).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))
            self.assertEqual(state.ServiceCategory.get(CATEGORY_1_ID).title, CATEGORY_1_TITLE)

    def test_load(self):
        with patch('features.services.state.people_category_select_all', _return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})

        with patch('features.services.state.people_category_select_all', _return_single_category):
            state.ServiceCategory.load()
            self.assertEqual(len(state.ServiceCategory._categories), 1)

        with patch('features.services.state.people_category_select_all', _return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})


class TestService(unittest.TestCase):
    def setUp(self):
        with patch('features.services.state.people_category_select_all', _return_single_category):
            state.ServiceCategory.load()

    def tearDown(self):
        with patch('features.services.state.people_category_select_all', _return_no_categories):
            state.ServiceCategory.load()

    @staticmethod
    def _return_service(tg_id: int, category_id: int) -> list:
        return [{"tg_id": SERVICE_10001_TG_ID, "tg_username": SERVICE_10001_TG_USERNAME, "category_id": CATEGORY_1_ID,
                 "occupation": "Occupation", "description": "Desciption", "location": "Location", "is_suspended": False,
                 "last_modified": SERVICE_10001_LAST_MODIFIED}]

    def test_get(self):
        with patch('features.services.state.service_get', self._return_service):
            service = state.Service.get(1, 1)

            self.assertEqual(service.category.id, CATEGORY_1_ID)
            self.assertEqual(service.category.title, CATEGORY_1_TITLE)
            self.assertEqual(service.tg_id, SERVICE_10001_TG_ID)
