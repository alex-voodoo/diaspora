"""
Database stuff
"""
import logging
import os
import pathlib
import sqlite3
from collections.abc import Iterator
from sqlite3 import Connection

from .log import LogTime
from .settings import settings

db_connection: Connection

_DB_FILENAME = settings.data_dir() / "people.db"


def _init() -> None:
    """Initialise the database if necessary

    Ensures that the database is ready to use by the application:
    Apply migrations prepared at the given path

    Enumerates all files with .txt extension at the given path, and tries to execute each one as a sequence of SQL
    statements, going through files in alphabetical order.

    Every file should contain one or more SQL statements separated with semicolon.
    """

    c = db_connection.cursor()

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

    db_connection.commit()

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

    db_connection.commit()


def connect() -> None:
    """Initialise the DB connection"""

    global db_connection
    db_connection = sqlite3.connect(_DB_FILENAME)

    _init()


def disconnect() -> None:
    """Terminate the DB connection"""

    db_connection.close()


def people_delete(tg_id: int, category_id: int) -> None:
    """Delete the user record identified by `tg_id`"""

    with LogTime("DELETE FROM people WHERE tg_id=? AND category_id=?"):
        c = db_connection.cursor()

        c.execute("DELETE FROM people WHERE tg_id=? AND category_id=?",
                  (tg_id, category_id))

        db_connection.commit()


def people_exists(td_ig: int) -> bool:
    """Return whether there a user record identified by `tg_id` exists in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?"):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_username, occupation, location FROM people WHERE tg_id=?", (td_ig,)):
            return True

        return False


def people_records(td_ig: int) -> Iterator:
    """Return all records of a user identified by `tg_id` existing in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?"):
        c = db_connection.cursor()

        for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.location "
                                "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                "WHERE p.tg_id=?", (td_ig,)):
            yield {key: value for (key, value) in zip(("title", "id", "occupation", "location"), record)}


def people_record(td_ig: int, category_id: int) -> Iterator:
    """Return a record of a user identified by `tg_id` and `category_id`"""

    with LogTime("SELECT FROM people WHERE tg_id=? AND category_id=?"):
        c = db_connection.cursor()

        for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.location "
                                "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                "WHERE p.tg_id=? AND pc.id=?", (td_ig, category_id)):
            yield {key: value for (key, value) in zip(("title", "id", "occupation", "location"), record)}


def people_insert_or_update(tg_id: int, tg_username: str, occupation: str, location: str, is_suspended: int,
                            category_id: int) -> None:
    """Create a new or update the existing record identified by `tg_id` in the `people` table"""

    with LogTime("INSERT OR REPLACE INTO people"):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO people "
                  "(tg_id, tg_username, occupation, location, is_suspended, category_id) "
                  "VALUES(?, ?, ?, ?, ?, ?)",
                  (tg_id, tg_username, occupation, location, is_suspended, category_id))

        db_connection.commit()


def people_approve(tg_id: int, category_id: int) -> None:
    """Set `is_suspended` to 0 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=0"):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=0 WHERE tg_id=? AND category_id=?", (tg_id, category_id))

        db_connection.commit()


def people_suspend(tg_id: int, category_id: int) -> None:
    """Set `is_suspended` to 1 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=1"):
        c = db_connection.cursor()

        c.execute("UPDATE people SET is_suspended=1 WHERE tg_id=? AND category_id=?", (tg_id, category_id))

        db_connection.commit()


def people_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people"):
        c = db_connection.cursor()

        # noinspection SpellCheckingInspection
        for row in c.execute("SELECT tg_id, tg_username, occupation, location, category_id FROM people "
                             "WHERE is_suspended=0 "
                             "ORDER BY tg_username COLLATE NOCASE"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def people_category_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people_category"):
        c = db_connection.cursor()

        for row in c.execute("SELECT id, title FROM people_category"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def register_good_member(tg_id: int) -> None:
    """Register the user ID in the `antispam_allowlist` table"""

    with LogTime("INSERT OR REPLACE INTO antispam_allowlist"):
        c = db_connection.cursor()

        c.execute("INSERT OR REPLACE INTO antispam_allowlist (tg_id) VALUES(?)", (tg_id,))

        db_connection.commit()


def is_good_member(tg_id: int) -> bool:
    """Return whether the user ID exists in the `antispam_allowlist` table"""

    with LogTime("SELECT FROM antispam_allowlist WHERE tg_id=?"):
        c = db_connection.cursor()

        for _ in c.execute("SELECT tg_id FROM antispam_allowlist WHERE tg_id=?", (tg_id,)):
            return True

        return False


def spam_insert(text: str, from_user_tg_id: int, trigger: str, confidence: float) -> None:
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
