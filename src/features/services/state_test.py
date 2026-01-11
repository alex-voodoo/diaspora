"""
Tests for state.py
"""

import unittest
from unittest.mock import patch

from common import i18n
from . import state

class TestServiceCategory(unittest.TestCase):
    CATEGORY_1_ID = 1
    CATEGORY_1_TITLE = "Category 1"

    def tearDown(self):
        with patch('features.services.state.people_category_select_all', self._return_no_categories):
            state.ServiceCategory.load()

    @staticmethod
    def _return_no_categories():
        return []

    @staticmethod
    def _return_single_category():
        return [{"id": TestServiceCategory.CATEGORY_1_ID, "title": TestServiceCategory.CATEGORY_1_TITLE}]

    def test_get(self):
        trans = i18n.default()

        self.assertEqual(state.ServiceCategory.get(0, trans).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))

        with self.assertRaises(KeyError):
            _category = state.ServiceCategory.get(TestServiceCategory.CATEGORY_1_ID, trans)


        with patch('features.services.state.people_category_select_all', self._return_single_category):
            state.ServiceCategory.load()

            self.assertEqual(state.ServiceCategory.get(0, trans).title, trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"))
            self.assertEqual(state.ServiceCategory.get(TestServiceCategory.CATEGORY_1_ID, trans).title, TestServiceCategory.CATEGORY_1_TITLE)

    def test_load(self):
        with patch('features.services.state.people_category_select_all', self._return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})

        with patch('features.services.state.people_category_select_all', self._return_single_category):
            state.ServiceCategory.load()
            self.assertEqual(len(state.ServiceCategory._categories), 1)

        with patch('features.services.state.people_category_select_all', self._return_no_categories):
            state.ServiceCategory.load()
            self.assertEqual(state.ServiceCategory._categories, {})
