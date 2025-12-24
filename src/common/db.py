"""
Database stuff
"""

import logging
import os
import pathlib
import sqlite3
from collections.abc import Iterator
from sqlite3 import Connection, Cursor

from .log import LogTime
from .settings import settings

_db_connection: Connection

_DB_FILENAME = "people.db"


def _init() -> None:
    """Initialise the database if necessary

    Ensures that the database is ready to use by the application:
    Apply migrations prepared at the given path

    Enumerates all files with .txt extension at the given path, and tries to execute each one as a sequence of SQL
    statements, going through files in alphabetical order.

    Every file should contain one or more SQL statements separated with semicolon.
    """

    c = _db_connection.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS \"people\" ("
              "\"tg_id\" INTEGER,"
              "\"tg_username\" TEXT,"
              "\"occupation\" TEXT,"
              "\"location\" TEXT,"
              "\"last_modified\" DATETIME DEFAULT CURRENT_TIMESTAMP,"
              "\"is_suspended\" INTEGER DEFAULT 0,"
              "PRIMARY KEY(\"tg_id\"))")
    c.execute("CREATE TABLE IF NOT EXISTS \"antispam_allowlist\" ("
              "\"tg_id\" INTEGER,"
              "PRIMARY KEY(\"tg_id\"))")
    c.execute("CREATE TABLE IF NOT EXISTS \"spam\" ("
              "\"id\" INTEGER,"
              "\"text\" TEXT,"
              "\"from_user_tg_id\" INTEGER,"
              "\"trigger\" TEXT,"
              "\"timestamp\" DATETIME DEFAULT CURRENT_TIMESTAMP,"
              "PRIMARY KEY(\"id\" AUTOINCREMENT))")

    _db_connection.commit()

    migrations_directory = pathlib.Path(__file__).parent.parent / "migrations"

    if not migrations_directory.exists() or not migrations_directory.is_dir():
        logging.warning(f"Directory {migrations_directory} does not exist, not applying any migrations")
        return

    c.execute("CREATE TABLE IF NOT EXISTS \"migrations\" ("
              "\"name\" TEXT UNIQUE,"
              "PRIMARY KEY(\"name\")"
              ")")

    migration_filenames = sorted(filename for filename in os.listdir(migrations_directory) if filename.endswith(".txt"))
    for migration_filename in migration_filenames:
        skip = False
        for _ in c.execute("SELECT name FROM migrations WHERE name=?", (migration_filename,)):
            logging.info("Migration {filename} is already applied, skipping".format(filename=migration_filename))
            skip = True

        if skip:
            continue

        with open(migrations_directory / migration_filename) as inp:
            logging.info(f"Applying migration {migration_filename}")

            migration = inp.read().split(";")
            for sql in migration:
                logging.info(f"Executing: {sql}")
                c.execute(sql)

            c.execute("INSERT INTO migrations(name) VALUES(?)", (migration_filename,))

    _db_connection.commit()


def connect() -> None:
    """Initialise the DB connection"""

    global _db_connection

    _db_connection = sqlite3.connect(settings.data_dir / _DB_FILENAME)

    _init()


def disconnect() -> None:
    """Terminate the DB connection"""

    _db_connection.close()


def cursor() -> Cursor:
    """Return a cursor for querying the database"""

    return _db_connection.cursor()


def commit() -> None:
    """Commit transactions pending on open connections to the DB"""

    _db_connection.commit()


def register_good_member(tg_id: int) -> None:
    """Register the user ID in the `antispam_allowlist` table"""

    with LogTime("INSERT OR REPLACE INTO antispam_allowlist"):
        c = _db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO antispam_allowlist (tg_id) VALUES(?)", (tg_id,))

        _db_connection.commit()


def is_good_member(tg_id: int) -> bool:
    """Return whether the user ID exists in the `antispam_allowlist` table"""

    with LogTime("SELECT FROM antispam_allowlist WHERE tg_id=?"):
        c = _db_connection.cursor()

        for _ in c.execute("SELECT tg_id FROM antispam_allowlist WHERE tg_id=?", (tg_id,)):
            return True

        return False


def spam_insert(text: str, from_user_tg_id: int, trigger: str, confidence: float) -> None:
    """Save a message that triggered antispam"""

    with LogTime("INSERT INTO spam"):
        c = _db_connection.cursor()

        c.execute("INSERT INTO spam (text, from_user_tg_id, trigger, openai_confidence) VALUES(?, ?, ?, ?)",
                  (text, from_user_tg_id, trigger, confidence))

        _db_connection.commit()


def spam_select_all() -> Iterator:
    """Query all records from the `spam` table"""

    with LogTime("SELECT text, from_user_tg_id, trigger, timestamp, openai_confidence FROM spam"):
        c = _db_connection.cursor()

        for row in c.execute("SELECT text, from_user_tg_id, trigger, timestamp, openai_confidence FROM spam"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}
