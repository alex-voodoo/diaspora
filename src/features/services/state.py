"""
Persistent state of the services feature
"""
from collections.abc import Iterator

from common import db
from common.log import LogTime


def people_delete(tg_id: int, category_id: int) -> None:
    """Delete the user record identified by `tg_id`"""

    with LogTime("DELETE FROM people WHERE tg_id=? AND category_id=?"):
        c = db.cursor()

        c.execute("DELETE FROM people WHERE tg_id=? AND category_id=?",
                  (tg_id, category_id))

        db.commit()


def people_exists(td_ig: int) -> bool:
    """Return whether there a user record identified by `tg_id` exists in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?"):
        c = db.cursor()

        for _ in c.execute("SELECT tg_username FROM people WHERE tg_id=?", (td_ig,)):
            return True

        return False


def people_records(td_ig: int) -> Iterator:
    """Return all records of a user identified by `tg_id` existing in the `people` table"""

    with LogTime("SELECT FROM people WHERE tg_id=?"):
        c = db.cursor()

        for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.description, p.location "
                                "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                "WHERE p.tg_id=?", (td_ig,)):
            yield {key: value for (key, value) in zip(("title", "id", "occupation", "description", "location"), record)}


def people_record(category_id: int, tg_id: int = 0, tg_username: str = "") -> Iterator:
    """Return a record of a user identified by `category_id` and either `tg_id` or `tg_username` """

    if tg_id != 0:
        with LogTime("SELECT FROM people WHERE tg_id=? AND category_id=?"):
            c = db.cursor()

            for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.description, p.location "
                                    "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                    "WHERE p.tg_id=? AND p.category_id=?", (tg_id, category_id)):
                yield {key: value for (key, value) in
                       zip(("title", "id", "occupation", "description", "location"), record)}
    elif tg_username != "":
        with LogTime("SELECT FROM people WHERE tg_username=? AND category_id=?"):
            c = db.cursor()

            for record in c.execute("SELECT pc.title, pc.id, p.occupation, p.description, p.location "
                                    "FROM people p LEFT JOIN people_category pc ON p.category_id = pc.id "
                                    "WHERE p.tg_username=? AND p.category_id=?", (tg_username, category_id)):
                yield {key: value for (key, value) in
                       zip(("title", "id", "occupation", "description", "location"), record)}


def people_insert_or_update(tg_id: int, tg_username: str, occupation: str, description: str, location: str,
                            is_suspended: int, category_id: int) -> None:
    """Create a new or update the existing record identified by `tg_id` in the `people` table"""

    with LogTime("INSERT OR REPLACE INTO people"):
        db.cursor().execute("INSERT OR REPLACE INTO people "
                            "(tg_id, tg_username, occupation, description, location, is_suspended, category_id) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?)",
                            (tg_id, tg_username, occupation, description, location, is_suspended, category_id))

        db.commit()


def people_approve(tg_id: int, category_id: int) -> None:
    """Set `is_suspended` to 0 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=0"):
        db.cursor().execute("UPDATE people "
                            "SET is_suspended=0 "
                            "WHERE tg_id=? AND category_id=?", (tg_id, category_id))

        db.commit()


def people_suspend(tg_id: int, category_id: int) -> None:
    """Set `is_suspended` to 1 for the user record identified by `tg_id`"""

    with LogTime("UPDATE people SET is_suspended=1"):
        db.cursor().execute("UPDATE people "
                            "SET is_suspended=1 "
                            "WHERE tg_id=? AND category_id=?", (tg_id, category_id))

        db.commit()


def people_select_all_active() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people WHERE is_suspended=0"):
        c = db.cursor()

        # noinspection SpellCheckingInspection
        for row in c.execute("SELECT tg_id, tg_username, occupation, location, category_id FROM people "
                             "WHERE is_suspended=0 "
                             "ORDER BY tg_username COLLATE NOCASE"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def people_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people"):
        c = db.cursor()

        # noinspection SpellCheckingInspection
        for row in c.execute("SELECT * FROM people "
                             "ORDER BY tg_username COLLATE NOCASE"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def people_category_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people_category"):
        c = db.cursor()

        for row in c.execute("SELECT id, title FROM people_category"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def import_db(new_data) -> None:
    cursor = db.cursor()

    cursor.execute("CREATE TABLE old_people_category AS SELECT * FROM people_category")
    cursor.execute("CREATE TABLE old_people AS SELECT * FROM people")

    cursor.execute("DELETE FROM people_category")
    for c in new_data["categories"]:
        cursor.execute("INSERT INTO people_category (id, title) "
                  "VALUES(?, ?)",
                  (c["id"], c["title"]))

    cursor.execute("DELETE FROM people")
    for p in new_data["people"]:
        cursor.execute(
            "INSERT INTO people (tg_id, tg_username, category_id, is_suspended, last_modified, occupation, description, location) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (p["tg_id"], p["tg_username"], p["category_id"], p["is_suspended"], p["last_modified"], p["occupation"],
             p["description"], p["location"]))

    db.commit()

    cursor.execute("DROP TABLE old_people_category")
    cursor.execute("DROP TABLE old_people")

    db.commit()
