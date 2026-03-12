import pathlib
import tempfile
import unittest

from common import db

class TestDbGeneral(unittest.TestCase):
    @staticmethod
    def test_connect_and_apply_migrations():
        with tempfile.NamedTemporaryFile(delete_on_close=False) as test_db_file:
            test_db_file.close()

            db.connect(pathlib.Path(test_db_file.name))
            db.disconnect()
