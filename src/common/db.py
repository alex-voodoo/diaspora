"""
Database stuff
"""

import logging
import os
import pathlib
import shutil
import sqlite3
import subprocess
from collections.abc import Iterator
from sqlite3 import Connection, Cursor

from .log import LogTime
from .settings import settings

_db_connection: Connection

def _apply_migrations() -> None:
    """Apply pending migrations

    Enumerates all files with .txt extension in the migrations directory, detects ones not applied previously, and tries
    to execute each one of them as a sequence of SQL statements, going through files in alphabetical order.

    Every file should contain one or more SQL statements separated by semicolons.
    """

    c = _db_connection.cursor()

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


def _format_log_query(query: str, parameters: tuple):
    if not parameters:
        return query
    params = []
    for p in parameters:
        fixed_p = p if not (type(p) == str and len(p) > 20) else p[:20]
        params.append(f"\"{fixed_p}\"" if type(fixed_p) == str else str(fixed_p))
    return f"{query} ({", ".join(params)})"


def connect(path: pathlib.Path = None) -> None:
    """Initialise the DB connection

    @param path: optional path to the SQLite3 database file.  If omitted, the standard path is used (see below).

    During development, to ease switching between branches that may be using different DB schemas, separate database
    files are used for each distinct branch or snapshot. The main branch uses the standard filename, for other branches
    it is modified by adding a suffix to the name. The algorithm is as follows:
    - If git cannot be executed, or the current branch is "main", the modifier is empty. The default name is used, and
      the database either already exists or is created empty.
    - Else if the branch name is "HEAD", then we are in the "detached head" state, and the short commit hash is used.
      This may be any arbitrary position in the commit history, so the only safe way is using a unique database created
      for this particular snapshot.
    - Else the name of the branch is used, and in this case a copy of the existing "main" database can be used initially
      when the program is started at this branch the first time.
    """

    global _db_connection

    standard_filename = "people.db"

    if path:
        effective_path = path
    else:
        copy_existing_db = False
        try:
            branch_name = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode("utf-8").strip()
            if branch_name == "HEAD":
                filename_mod = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("utf-8").strip()
            elif branch_name == "main":
                filename_mod = ""
            else:
                filename_mod = branch_name.replace("/", "_")
                copy_existing_db = True
        except FileNotFoundError:
            logging.info("Could not run git, assuming this is a production deployment, using the standard DB filename")
            filename_mod= ""
        except subprocess.CalledProcessError:
            logging.info("Error calling git, using the standard DB filename")
            filename_mod= ""

        standard_path = settings.data_dir / standard_filename
        effective_path = settings.data_dir / ".".join(filter(None, ["people", filename_mod, "db"]))

        if copy_existing_db and os.path.exists(standard_path) and not os.path.exists(effective_path):
            logging.info("Running on a branch the first time, copying an existing DB")
            shutil.copy(standard_path, effective_path)

    logging.info(f"Will use the database: {effective_path}")
    _db_connection = sqlite3.connect(effective_path)

    _apply_migrations()


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


def sql_exec(query: str, parameters: tuple = ()) -> None:
    """Execute an SQL query that does not return data

    @param query: SQL query with placeholders for bound parameters
    @param parameters: data to bind

    `query` and `parameters` are passed directly to `sqlite3.Cursor.execute()` method.

    Commits the transaction immediately after executing the query.
    """

    with LogTime(_format_log_query(query, parameters)):
        cursor().execute(query, parameters)
        commit()


def sql_query(query: str, parameters: tuple = ()) -> Iterator[dict]:
    """Execute an SQL query that returns data

    @param query: SQL query with placeholders for bound parameters
    @param parameters: data to bind

    `query` and `parameters` are passed directly to `sqlite3.Cursor.execute()` method.
    """

    with LogTime(_format_log_query(query, parameters)):
        c = cursor()
        for record in c.execute(query, parameters):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), record)}
