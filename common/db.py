"""
Database stuff
"""

import logging
import sqlite3
import time
from collections.abc import Iterator
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


def people_delete(tg_id) -> None:
    """Delete the user record identified by `tg_id`"""

    with LogTime("DELETE FROM people WHERE tg_id=?"):
        c = db_connection.cursor()

        c.execute("DELETE FROM people WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def people_exists(td_ig) -> bool:
    """Return whether there a user record identified by `tg_id` exists in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?"):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_username, occupation, location FROM people WHERE tg_id=?", (td_ig,)):
            return True

        return False


def people_insert_or_update(tg_id, tg_username, occupation, location, is_suspended) -> None:
    """Create a new or update the existing record identified by `tg_id` in the `people` table"""

    with LogTime("INSERT OR REPLACE INTO people"):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, location, is_suspended) "
                  "VALUES(?, ?, ?, ?, ?)", (tg_id, tg_username, occupation, location, is_suspended))

        db_connection.commit()


def people_approve(tg_id) -> None:
    """Set `is_suspended` to 0 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=0"):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=0 WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def people_suspend(tg_id) -> None:
    """Set `is_suspended` to 1 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=1"):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=1 WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def people_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people"):
        c = db_connection.cursor()

        for row in c.execute("SELECT tg_id, tg_username, occupation, location FROM people WHERE is_suspended=0"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def register_good_member(tg_id) -> None:
    """Register the user ID in the `antispam_allowlist` table"""

    with LogTime("INSERT OR REPLACE INTO antispam_allowlist"):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO antispam_allowlist (tg_id) VALUES(?)", (tg_id,))

        db_connection.commit()


def is_good_member(tg_id) -> bool:
    """Return whether the user ID exists in the `antispam_allowlist` table"""

    with LogTime("SELECT FROM antispam_allowlist WHERE tg_id=?"):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_id FROM antispam_allowlist WHERE tg_id=?", (tg_id,)):
            return True

        return False


def spam_insert(text, from_user_tg_id, trigger, confidence) -> None:
    """Save a message that triggered antispam"""

    with LogTime("INSERT INTO spam"):
        c = db_connection.cursor()

        c.execute("INSERT INTO spam (text, from_user_tg_id, trigger, openai_confidence) VALUES(?, ?, ?, ?)",
                  (text, from_user_tg_id, trigger, confidence))

        db_connection.commit()

def spam_select_all() -> Iterator:
    """Query all records from the `spam` table"""

    with LogTime("SELECT text, from_user_tg_id, trigger, timestamp, openai_confidence FROM spam"):
        c = db_connection.cursor()

        for row in c.execute("SELECT text, from_user_tg_id, trigger, timestamp, openai_confidence FROM spam"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def select_industry_data() -> Iterator:
    """Query all records from the `dict_data` table industry dictionary"""

    with LogTime("SELECT term FROM dict_data where dict_id = 1"):
        c = db_connection.cursor()

        for row in c.execute("SELECT term FROM dict_data where dict_id = 1"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}
