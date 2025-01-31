"""
Database stuff
"""

import logging
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection

from common.log_time import LogTime

db_connection: Connection

db_logger = logging.getLogger("db")
db_logging_handler = logging.FileHandler("db.log")
# noinspection SpellCheckingInspection
db_logging_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
db_logger.addHandler(db_logging_handler)
db_logger.propagate = False


def apply_migrations(migrations_directory: Path) -> None:
    conn = sqlite3.connect("people.db")
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS \"migrations\" ("
              "\"name\" TEXT UNIQUE,"
              "PRIMARY KEY(\"name\")"
              ")")

    migration_filenames = sorted(filename for filename in os.listdir(migrations_directory) if filename.endswith(".txt"))
    for migration_filename in migration_filenames:
        skip = False
        for _ in c.execute("SELECT name FROM migrations WHERE name=?", (migration_filename,)):
            print("Migration {filename} is already applied, skipping".format(filename=migration_filename))
            skip = True

        if skip:
            continue

        with open(migrations_directory / migration_filename) as inp:
            print("Applying migration {filename}".format(filename=migration_filename))

            migration = inp.read().split(";")
            for sql in migration:
                print(sql)
                c.execute(sql)

            c.execute("INSERT INTO migrations(name) VALUES(?)", (migration_filename,))

    conn.commit()
    conn.close()


def connect() -> None:
    """Initialise the DB connection"""

    global db_connection
    db_connection = sqlite3.connect("people.db")


def disconnect() -> None:
    """Terminate the DB connection"""

    db_connection.close()


def people_delete(tg_id: int, category_id: int) -> None:
    """Delete the user record identified by `tg_id`"""

    with LogTime("DELETE FROM people WHERE tg_id=? AND category_id=?", db_logger):
        c = db_connection.cursor()

        c.execute("DELETE FROM people WHERE tg_id=? AND category_id=?",
                  (tg_id, category_id))

        db_connection.commit()


def people_exists(td_ig: int) -> bool:
    """Return whether there a user record identified by `tg_id` exists in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?", db_logger):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_username, occupation, location FROM people WHERE tg_id=?", (td_ig,)):
            return True

        return False


def people_records(td_ig: int) -> Iterator:
    """Return all records of a user identified by `tg_id` existing in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?", db_logger):
        c = db_connection.cursor()

        for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.location "
                                "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                "WHERE p.tg_id=?", (td_ig,)):
            yield {key: value for (key, value) in zip(("title", "id", "occupation", "location"), record)}


def people_record(td_ig: int, category_id: int) -> Iterator:
    """Return a record of a user identified by `tg_id` and `category_id`"""

    with LogTime("SELECT FROM people WHERE tg_id=? AND category_id=?", db_logger):
        c = db_connection.cursor()

        for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.location "
                                "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                "WHERE p.tg_id=? AND pc.id=?", (td_ig, category_id)):
            yield {key: value for (key, value) in zip(("title", "id", "occupation", "location"), record)}


def people_insert_or_update(tg_id: int, tg_username: str, occupation: str, location: str, is_suspended: int,
                            category_id: int) -> None:
    """Create a new or update the existing record identified by `tg_id` in the `people` table"""

    with LogTime("INSERT OR REPLACE INTO people", db_logger):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO people "
                  "(tg_id, tg_username, occupation, location, is_suspended, category_id) "
                  "VALUES(?, ?, ?, ?, ?, ?)",
                  (tg_id, tg_username, occupation, location, is_suspended, category_id))

        db_connection.commit()


def people_approve(tg_id: int) -> None:
    """Set `is_suspended` to 0 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=0", db_logger):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=0 WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def people_suspend(tg_id: int) -> None:
    """Set `is_suspended` to 1 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=1", db_logger):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=1 WHERE tg_id=?", (tg_id,))

        db_connection.commit()


def people_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people", db_logger):
        c = db_connection.cursor()

        # noinspection SpellCheckingInspection
        for row in c.execute("SELECT tg_id, tg_username, occupation, location, category_id FROM people "
                             "WHERE is_suspended=0 "
                             "ORDER BY tg_username COLLATE NOCASE"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def people_category_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people_category", db_logger):
        c = db_connection.cursor()

        for row in c.execute("SELECT id, title FROM people_category"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def register_good_member(tg_id: int) -> None:
    """Register the user ID in the `antispam_allowlist` table"""

    with LogTime("INSERT OR REPLACE INTO antispam_allowlist", db_logger):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO antispam_allowlist (tg_id) VALUES(?)", (tg_id,))

        db_connection.commit()


def is_good_member(tg_id: int) -> bool:
    """Return whether the user ID exists in the `antispam_allowlist` table"""

    with LogTime("SELECT FROM antispam_allowlist WHERE tg_id=?", db_logger):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_id FROM antispam_allowlist WHERE tg_id=?", (tg_id,)):
            return True

        return False


def spam_insert(text: str, from_user_tg_id: int, trigger: str, confidence: float) -> None:
    """Save a message that triggered antispam"""

    with LogTime("INSERT INTO spam", db_logger):
        c = db_connection.cursor()

        c.execute("INSERT INTO spam (text, from_user_tg_id, trigger, openai_confidence) VALUES(?, ?, ?, ?)",
                  (text, from_user_tg_id, trigger, confidence))

        db_connection.commit()


def spam_select_all() -> Iterator:
    """Query all records from the `spam` table"""

    with LogTime("SELECT text, from_user_tg_id, trigger, timestamp, openai_confidence FROM spam", db_logger):
        c = db_connection.cursor()

        for row in c.execute("SELECT text, from_user_tg_id, trigger, timestamp, openai_confidence FROM spam"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}
