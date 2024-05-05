"""
Database stuff
"""

import logging
import sqlite3
import time
from sqlite3 import Connection

db_connection: Connection


class LogTime:
    """Time measuring context manager, logs time elapsed while executing the context

    Usage:

        with LogTime("<task>"):
            ...

    The above will log: "<task> took X ms".
    """

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.started_at = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.perf_counter() - self.started_at) * 1000
        time_logger = logging.getLogger("time")
        time_logger.info("{name} took {elapsed} ms".format(name=self.name, elapsed=elapsed))


def connect() -> None:
    """Initialise the DB connection"""

    global db_connection
    db_connection = sqlite3.connect("people.db")


def disconnect() -> None:
    """Terminate the DB connection"""

    db_connection.close()


def delete_user_record(tg_id) -> None:
    """Delete the user record identified by `tg_id`"""

    with LogTime("DELETE FROM people WHERE tg_id=?"):
        c = db_connection.cursor()

        c.execute("DELETE FROM people WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def has_user_record(td_ig) -> bool:
    """Return whether there a user record identified by `tg_id` exists in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?"):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_username, occupation, location FROM people WHERE tg_id=?", (td_ig,)):
            return True

        return False


def create_or_update_user_record(tg_id, tg_username, occupation, location, is_suspended) -> None:
    """Create a new or update the existing record identified by `tg_id` in the `people` table"""

    with LogTime("INSERT OR REPLACE INTO people"):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, location, is_suspended) "
                  "VALUES(?, ?, ?, ?, ?)", (tg_id, tg_username, occupation, location, is_suspended))

        db_connection.commit()


def approve_user_record(tg_id) -> None:
    """Set `is_suspended` to 0 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=0"):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=0 WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def suspend_user_record(tg_id):
    """Set `is_suspended` to 1 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=1"):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=1 WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def people_get_all():
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people"):
        c = db_connection.cursor()

        for row in c.execute("SELECT tg_id, tg_username, occupation, location FROM people WHERE is_suspended=0"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def register_good_member(tg_id):
    """Register the user ID in the `antispam_allowlist` table"""

    with LogTime("INSERT OR REPLACE INTO antispam_allowlist"):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO antispam_allowlist (tg_id) VALUES(?)", (tg_id,))

        db_connection.commit()


def is_good_member(tg_id):
    """Return whether the user ID exists in the `antispam_allowlist` table"""

    with LogTime("SELECT FROM antispam_allowlist WHERE tg_id=?"):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_id FROM antispam_allowlist WHERE tg_id=?", (tg_id,)):
            return True

        return False


def save_spam(text, from_user_tg_id, trigger):
    """Save a message that triggered antispam"""

    with LogTime("INSERT INTO spam"):
        c = db_connection.cursor()

        c.execute("INSERT INTO spam (text, from_user_tg_id, trigger) VALUES(?, ?, ?)",
                  (text, from_user_tg_id, trigger))

        db_connection.commit()
