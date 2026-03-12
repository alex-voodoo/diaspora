import json
import pathlib
import tempfile
import unittest

import jsonschema

from common import db
from .test_util import *


class TestAdmin(unittest.TestCase):
    def test_export_and_import(self):
        with tempfile.NamedTemporaryFile(delete_on_close=False) as test_db_file:
            test_db_file.close()

            db.connect(pathlib.Path(test_db_file.name))

            data = state.export_db()

            data["categories"].append(data_row_for_service_category(1))
            data["categories"].append(data_row_for_service_category(2))

            state.import_db(data)

            tg_id_1125 = 1125
            tg_id_235126 = 235126
            for tg_id in [tg_id_1125, tg_id_235126]:
                state.Provider.create(tg_id, test_tg_username(tg_id))

            for tg_id in [tg_id_1125, tg_id_235126]:
                state.Service.set(tg_id, test_occupation(tg_id), test_description(tg_id), test_location(tg_id),
                                  test_is_suspended(tg_id), 1)

            data = state.export_db()

            with open(pathlib.Path(__file__).parent / "schema.json") as schema_file:
                schema = json.load(schema_file)
            jsonschema.validate(data, schema)

            tg_id_4235 = 4235
            state.Provider.create(tg_id_4235, test_tg_username(tg_id_4235))

            for tg_id in [tg_id_1125, tg_id_235126]:
                state.Service.set(tg_id, test_occupation(tg_id), test_description(tg_id), test_location(tg_id),
                                  test_is_suspended(tg_id), 2)

            state.import_db(data)

            state.Provider.get_by_tg_id(tg_id_1125)
            state.Provider.get_by_tg_id(tg_id_235126)

            with self.assertRaises(state.Provider.NotFound):
                state.Provider.get_by_tg_id(tg_id_4235)

            for tg_id in [tg_id_1125, tg_id_235126]:
                state.Service.get(tg_id, 1)
                with self.assertRaises(state.Service.NotFound):
                    state.Service.get(tg_id, 2)

            db.disconnect()
