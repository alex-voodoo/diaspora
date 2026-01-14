"""
Persistent state of the services feature
"""

import datetime
import logging
from collections.abc import Iterator
from typing import Self

from common import db, i18n
from common.log import LogTime


class ServiceCategory:
    """Wraps a service category database record

    The class caches the entire `people_category` table and provides a `get()` method for accessing individual items.

    The storage must be initialised by calling the `load()` class method.
    """

    _categories = {}

    def __init__(self, db_id: int, title: str):
        self._id = db_id
        self._title = title

    @property
    def id(self) -> int:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @classmethod
    def get(cls, db_id: int) -> Self:
        """Get a service category identified by `db_id`

        Returns a "default category" object iff `db_id` is equal to 0.
        Raises `KeyError` if no object found for the given ID.
        """

        if db_id == 0:
            return ServiceCategory(0, i18n.default().gettext("SERVICES_CATEGORY_OTHER_TITLE"))
        return cls._categories[db_id]

    @classmethod
    def load(cls) -> None:
        """Load all service category records from the DB and store them in a class attribute"""

        cls._categories = {}

        for category in people_category_select_all():
            cls._categories[category["id"]] = ServiceCategory(category["id"], category["title"])

    @classmethod
    def count(cls) -> int:
        """Return number of categories"""

        return len(cls._categories)

    @classmethod
    def all(cls) -> Iterator[Self]:
        """Return all service categories"""

        for category in cls._categories.values():
            yield category


class Service:
    """Wraps a service database record"""

    _bot_username: str

    def __init__(self, **kwargs):
        self._tg_id = kwargs["tg_id"]
        self._tg_username = kwargs["tg_username"]
        self._category_id = kwargs["category_id"]
        self._occupation = kwargs["occupation"]
        self._description = kwargs["description"]
        self._location = kwargs["location"]
        self._is_suspended = kwargs["is_suspended"]
        self._last_modified = kwargs["last_modified"]

    @property
    def category(self) -> ServiceCategory:
        return ServiceCategory.get(self._category_id)

    @property
    def tg_id(self) -> int:
        return self._tg_id

    @property
    def tg_username(self) -> str:
        return self._tg_username

    @property
    def occupation(self) -> str:
        return self._occupation

    @property
    def description(self) -> str:
        return self._description

    @property
    def location(self) -> str:
        return self._location

    @property
    def is_suspended(self) -> bool:
        return self._is_suspended

    @property
    def last_modified(self) -> datetime.datetime:
        return self._last_modified

    @property
    def deep_link(self) -> str:
        return f"t.me/{Service._bot_username}?start=service_info_{self._category_id or 0}_{self._tg_username}"

    @classmethod
    def set_bot_username(cls, bot_username: str) -> None:
        Service._bot_username = bot_username

    @classmethod
    def get(cls, tg_id: int, category_id: int) -> Self:
        for service in _service_get(category_id, tg_id):
            return Service(**service)

    @classmethod
    def get_by_username(cls, tg_username: str, category_id: int) -> Self:
        for service in _service_get(category_id, tg_username=tg_username):
            return Service(**service)

    @classmethod
    def delete(cls, tg_id: int, category_id: int) -> None:
        _service_delete(tg_id, category_id)

    @classmethod
    def get_all_by_user(cls, tg_id) -> Iterator[Self]:
        for service in _service_get_all_by_user(tg_id):
            yield Service(**service)


def _service_select(where_clause: str, where_params: tuple) -> Iterator:
    fields = (
        "tg_id", "tg_username", "category_id", "occupation", "description", "location", "is_suspended", "last_modified")

    with LogTime(f"SELECT FROM people WHERE {where_clause}"):
        c = db.cursor()

        for record in c.execute(f"SELECT {", ".join(fields)} FROM PEOPLE WHERE {where_clause}", where_params):
            data = {key: value for (key, value) in zip(fields, record)}
            data["last_modified"] = datetime.datetime.fromisoformat(data["last_modified"])
            data["is_suspended"] = bool(data["is_suspended"])
            yield data


def _service_get(category_id: int, tg_id: int = 0, tg_username: str = "") -> Iterator:
    """Return a record of a user identified by `category_id` and either `tg_id` or `tg_username` """

    if tg_id != 0:
        where_clause = "tg_id=? AND category_id=?"
        where_params = (tg_id, category_id)
    elif tg_username != "":
        where_clause = "tg_username=? AND category_id=?"
        where_params = (tg_username, category_id)
    else:
        raise RuntimeError("Neither tg_id nor tg_username were defined")

    for record in _service_select(where_clause, where_params):
        yield record


def _service_delete(tg_id: int, category_id: int) -> None:
    """Delete the user record identified by `tg_id`"""

    with LogTime("DELETE FROM people WHERE tg_id=? AND category_id=?"):
        c = db.cursor()

        c.execute("DELETE FROM people WHERE tg_id=? AND category_id=?", (tg_id, category_id))

        db.commit()


def _service_get_all_by_user(tg_id: int) -> Iterator:
    """Return all records of a user identified by `tg_id` existing in the `people` table"""

    for record in _service_select("tg_id=?", (tg_id, )):
        yield record


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


def people_category(category_id: int) -> Iterator:
    """Query one category with the given ID"""

    with LogTime("SELECT * FROM people_category WHERE id=?"):
        c = db.cursor()

        for row in c.execute("SELECT id, title FROM people_category WHERE id=?", (category_id,)):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def people_category_select_all() -> Iterator:
    """Query all non-suspended records from the `people` table"""

    with LogTime("SELECT * FROM people_category"):
        c = db.cursor()

        for row in c.execute("SELECT id, title FROM people_category"):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}


def people_category_views_register(viewer_tg_id: int, category_id: int) -> None:
    """Register a single event of a user browsing a category

    @param viewer_tg_id: Telegram ID of a user that requests the information.
    @param category_id: ID of a category being viewed, -1 for the general view (no specific category was requested).
    """

    with LogTime("INSERT INTO people_category_views"):
        db.cursor().execute("INSERT INTO people_category_views (viewer_tg_id, category_id) VALUES(?, ?)",
                            (viewer_tg_id, category_id))
        db.commit()


def people_views_register(viewer_tg_id: int, tg_id: int, category_id: int) -> None:
    """Register a single event of a user viewing a service description

    @param viewer_tg_id: Telegram ID of a user that requests the information.
    @param tg_id: Telegram ID of a user whose service is being viewed.
    @param category_id: ID of a category of the service that is being viewed.
    """

    with LogTime("INSERT INTO people_views"):
        db.cursor().execute("INSERT INTO people_views (viewer_tg_id, tg_id, category_id) VALUES(?, ?, ?)",
                            (viewer_tg_id, tg_id, category_id))
        db.commit()


def import_db(new_data) -> None:
    cursor = db.cursor()

    import_timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%Z")
    categories_backup = f"people_category_{import_timestamp}"
    people_backup = f"people_{import_timestamp}"

    for query in (f"CREATE TABLE {categories_backup} AS SELECT * FROM people_category",
                  f"CREATE TABLE {people_backup} AS SELECT * FROM people"):
        with LogTime(query):
            cursor.execute(query)

    db.commit()

    logging.info(f"Saved current data into {categories_backup} and {people_backup}")

    cursor.execute("DELETE FROM people_category")
    for c in new_data["categories"]:
        cursor.execute("INSERT INTO people_category (id, title) "
                       "VALUES(?, ?)", (c["id"], c["title"]))

    cursor.execute("DELETE FROM people")
    for p in new_data["people"]:
        cursor.execute("INSERT INTO people (tg_id, tg_username, category_id, is_suspended, last_modified, occupation, "
                       "description, location) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (
                           p["tg_id"], p["tg_username"], p["category_id"], p["is_suspended"], p["last_modified"],
                           p["occupation"], p["description"], p["location"]))

    db.commit()

    logging.info("Loaded new data")

    cursor.execute(f"DROP TABLE {categories_backup}")
    cursor.execute(f"DROP TABLE {people_backup}")

    db.commit()

    logging.info("Dropped data snapshots")

    ServiceCategory.load()
