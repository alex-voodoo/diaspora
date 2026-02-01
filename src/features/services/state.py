"""
Persistent state of the services feature
"""

import datetime
import logging
from collections.abc import Iterator
from typing import Self

from common import db, i18n
from common.log import LogTime
from common.settings import settings


class ServiceCategory:
    """Wraps a service category database record

    The class caches the entire `people_category` table and provides methods for accessing individual items and the
    entire collection.

    The storage must be initialised by calling the `load()` class method.
    """

    _categories = {}
    _order = []

    # noinspection PyShadowingBuiltins
    def __init__(self, id: int, title: str):
        self._id = id
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

        for category in _service_category_select_all():
            cls._categories[category["id"]] = ServiceCategory(category["id"], category["title"])

        cls._order = [c.id for c in sorted(cls._categories.values(), key=lambda v: v.title)]

    @classmethod
    def count(cls) -> int:
        """Return number of categories"""

        return len(cls._categories)

    @classmethod
    def all(cls) -> Iterator[Self]:
        """Return all service categories sorted alphabetically by title (the default category goes in the end)"""

        for category_id in cls._order:
            yield cls.get(category_id)
        yield cls.get(0)


class Service:
    """Wraps a service database record"""

    class NotFound(Exception):
        pass

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
        raise Service.NotFound

    @classmethod
    def get_by_username(cls, tg_username: str, category_id: int) -> Self:
        for service in _service_get(category_id, tg_username=tg_username):
            return Service(**service)
        raise Service.NotFound

    @classmethod
    def get_all_active(cls) -> Iterator[Self]:
        for service in _service_get_all_active():
            yield Service(**service)

    @classmethod
    def set(cls, tg_id: int, tg_username: str, occupation: str, description: str, location: str, is_suspended: bool,
            category_id: int) -> None:
        _service_insert_or_update(tg_id, tg_username, occupation, description, location, 1 if is_suspended else 0,
                                  category_id)

    @classmethod
    def set_is_suspended(cls, tg_id: int, category_id: int, is_suspended: bool):
        _set_service_is_suspended(tg_id, category_id, is_suspended)

    @classmethod
    def delete(cls, tg_id: int, category_id: int) -> None:
        _service_delete(tg_id, category_id)

    @classmethod
    def get_all_by_user(cls, tg_id) -> Iterator[Self]:
        for service in _service_get_all_by_user(tg_id):
            yield Service(**service)


class ServiceCategoryStats:
    def __init__(self, category_id: int, view_count: int, viewer_count: int):
        self._category_id = category_id
        self._view_count = view_count
        self._viewer_count = viewer_count

    @property
    def category(self) -> ServiceCategory:
        if self._category_id >= 0:
            return ServiceCategory.get(self._category_id)
        return ServiceCategory(-1, i18n.default().gettext("SERVICES_CATEGORY_LIST_TITLE"))

    @property
    def view_count(self) -> int:
        return self._view_count

    @property
    def viewer_count(self) -> int:
        return self._viewer_count


def _sql_exec(query: str, parameters: tuple = ()) -> None:
    """Execute an SQL query that does not return data

    @param query: SQL query with placeholders for bound parameters
    @param parameters: data to bind

    `query` and `parameters` are passed directly to `sqlite3.Cursor.execute()` method.

    Commits the transaction immediately after executing the query.
    """

    with LogTime(query):
        db.cursor().execute(query, parameters)
        db.commit()


def _sql_query(query: str, parameters: tuple = ()) -> Iterator[dict]:
    """Execute an SQL query that returns data

    @param query: SQL query with placeholders for bound parameters
    @param parameters: data to bind

    `query` and `parameters` are passed directly to `sqlite3.Cursor.execute()` method.
    """

    with LogTime(query):
        c = db.cursor()
        for record in c.execute(query, parameters):
            yield {key: value for (key, value) in zip((i[0] for i in c.description), record)}


def _service_select(where_clause: str = "", where_params: tuple = (), additional_clause: str = "") -> Iterator[dict]:
    """Select services with optional clauses

    @param where_clause: what to put into SQL WHERE clause, with placeholders for bound parameters
    @param where_params: data to bind in the WHERE clause
    @param additional_clause: what to add after WHERE
    @return: data returned by the DB

    Executes an SQL SELECT query that selects all columns from the `people` table.  Converts data to their correct types
    (`last_modified` to datetime and `is_suspended` to bool).  Data is returned as a dictionary with keys compatible
    with `Service.__init__()`.
    """

    query = ["SELECT tg_id, tg_username, category_id, occupation, description, location, is_suspended, last_modified "
             "FROM people"]
    if where_clause:
        query.append(f"WHERE {where_clause}")
    if additional_clause:
        query.append(additional_clause)
    query = " ".join(query)

    for record in _sql_query(query, where_params):
        record["last_modified"] = datetime.datetime.fromisoformat(record["last_modified"])
        record["is_suspended"] = bool(record["is_suspended"])
        yield record


def _service_get(category_id: int, tg_id: int = 0, tg_username: str = "") -> Iterator[dict]:
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


def _service_get_all_active() -> Iterator[dict]:
    """Query all non-suspended records from the `people` table"""

    for record in _service_select("is_suspended=0", (), "ORDER BY tg_username COLLATE NOCASE"):
        yield record


def _service_get_all_by_user(tg_id: int) -> Iterator[dict]:
    """Return all records of a user identified by `tg_id` existing in the `people` table"""

    for record in _service_select("tg_id=?", (tg_id,)):
        yield record


def _service_delete(tg_id: int, category_id: int) -> None:
    """Delete the user record identified by `tg_id`"""

    _sql_exec("DELETE FROM people WHERE tg_id=? AND category_id=?", (tg_id, category_id))


def _service_insert_or_update(tg_id: int, tg_username: str, occupation: str, description: str, location: str,
                              is_suspended: int, category_id: int) -> None:
    """Create a new or update the existing record identified by `tg_id` in the `people` table"""

    _sql_exec("INSERT OR REPLACE INTO people (tg_id, tg_username, occupation, description, location, is_suspended, "
              "category_id) VALUES(?, ?, ?, ?, ?, ?, ?)",
              (tg_id, tg_username, occupation, description, location, is_suspended, category_id))


def _set_service_is_suspended(tg_id: int, category_id: int, is_suspended: bool) -> None:
    _sql_exec("UPDATE people SET is_suspended=? WHERE tg_id=? AND category_id=?", (is_suspended, tg_id, category_id))


def _service_category_select_all() -> Iterator:
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

    _sql_exec("INSERT INTO people_category_views (viewer_tg_id, category_id) VALUES(?, ?)", (viewer_tg_id, category_id))


def people_views_register(viewer_tg_id: int, tg_id: int, category_id: int) -> None:
    """Register a single event of a user viewing a service description

    @param viewer_tg_id: Telegram ID of a user that requests the information.
    @param tg_id: Telegram ID of a user whose service is being viewed.
    @param category_id: ID of a category of the service that is being viewed.
    """

    _sql_exec("INSERT INTO people_views (viewer_tg_id, tg_id, category_id) VALUES(?, ?, ?)",
              (viewer_tg_id, tg_id, category_id))


def people_category_views_report(from_date: datetime.datetime) -> Iterator[ServiceCategoryStats]:
    parameters = (from_date.strftime("%Y-%m-%d"),)
    if settings.SERVICES_STATS_INCLUDE_ADMINISTRATORS:
        query = ("SELECT category_id, COUNT(1) as view_count, COUNT(DISTINCT viewer_tg_id) as viewer_count "
                 "FROM people_category_views "
                 "WHERE timestamp > ? "
                 "GROUP BY category_id")
    else:
        admin_id_phds = ", ".join(["?"] * len(settings.ADMINISTRATORS))
        query = (f"SELECT category_id, COUNT(1) as view_count, COUNT(DISTINCT viewer_tg_id) as viewer_count "
                 f"FROM people_category_views "
                 f"WHERE timestamp > ?  AND viewer_tg_id NOT IN ({admin_id_phds}) "
                 f"GROUP BY category_id")
        parameters += tuple(admin["id"] for admin in settings.ADMINISTRATORS)

    for row in _sql_query(query, parameters):
        yield ServiceCategoryStats(**row)


def export_db() -> dict:
    def service_select_all() -> Iterator:
        """Query all non-suspended records from the `people` table"""

        with LogTime("SELECT * FROM people"):
            c = db.cursor()

            # noinspection SpellCheckingInspection
            for row in c.execute("SELECT * FROM people "
                                 "ORDER BY tg_username COLLATE NOCASE"):
                yield {key: value for (key, value) in zip((i[0] for i in c.description), row)}

    return {"categories": [category for category in _service_category_select_all()],
            "people": [person for person in service_select_all()]}


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
