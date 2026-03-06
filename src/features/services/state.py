"""
Persistent state of the services feature
"""

import datetime
import logging
from collections.abc import Iterator
from typing import Self

from common import db, i18n, util
from common.settings import settings


_CATEGORIES = "services_categories"
_PROVIDERS = "services_providers"
_SERVICES = "services_services"


class Provider:
    """Wraps a service provider database record

    Caches objects to minimise DB operations.
    """

    class NotFound(Exception):
        pass

    _id_index = {}
    _username_index = {}

    def __init__(self, **kwargs):
        self._tg_id = kwargs["tg_id"]
        self._tg_username = kwargs["tg_username"]
        self._next_ping = kwargs["next_ping"]

    @property
    def tg_id(self) -> int:
        return self._tg_id

    @property
    def tg_username(self) -> str:
        return self._tg_username

    @property
    def next_ping(self) -> datetime.datetime:
        return self._next_ping

    @classmethod
    def load(cls) -> None:
        """Load all service category records from the DB and store them in a class attribute"""

        cls._id_index = {}
        cls._username_index = {}

        for row in Provider._do_select_query(f"SELECT * FROM {_PROVIDERS}"):
            cls._cache(row)

    @classmethod
    def get_all(cls) -> Iterator[Self]:
        for provider in cls._id_index.values():
            yield provider

    @classmethod
    def get_by_tg_id(cls, tg_id: int) -> Self:
        if tg_id not in cls._id_index:
            raise Provider.NotFound
        return cls._id_index[tg_id]

    @classmethod
    def get_by_tg_username(cls, tg_username: str) -> Self:
        if tg_username not in cls._username_index:
            raise Provider.NotFound
        return cls._username_index[tg_username]

    @classmethod
    def create_or_update(cls, tg_id: int, tg_username: str, next_ping: datetime.datetime) -> None:
        db.sql_exec(
            f"INSERT OR REPLACE INTO {_PROVIDERS} (tg_id, tg_username, next_ping) "
            f"VALUES(?, ?, ?)", (tg_id, tg_username, util.db_format(next_ping)))
        if tg_id in cls._id_index:
            existing_provider = cls._id_index[tg_id]
            if tg_username != existing_provider.tg_username:
                del cls._username_index[existing_provider.tg_username]
                cls._username_index[tg_username] = existing_provider
                existing_provider._tg_username = tg_username
            existing_provider._next_ping = next_ping
        else:
            new_provider = Provider(tg_id=tg_id, tg_username=tg_username, next_ping=next_ping)
            cls._id_index[new_provider.tg_id] = new_provider
            cls._username_index[new_provider.tg_username] = new_provider

    @classmethod
    def delete(cls, tg_id: int) -> None:
        db.sql_exec(f"DELETE FROM {_PROVIDERS} WHERE tg_id=?", (tg_id,))

        existing_provider = cls._id_index[tg_id]
        del cls._username_index[existing_provider.tg_username]
        del cls._id_index[tg_id]

    @classmethod
    def _cache(cls, data):
        provider = Provider(**data)
        cls._id_index[provider.tg_id] = provider
        cls._username_index[provider.tg_username] = provider
        return provider

    @staticmethod
    def _do_select_query(query: str, parameters: tuple = ()) -> Iterator[dict]:
        for row in db.sql_query(query, parameters):
            row["next_ping"] = datetime.datetime.fromisoformat(row["next_ping"])
            yield row


class ServiceCategory:
    """Wraps a service category database record

    The class caches the entire `services_categories` table and provides methods for accessing individual items and the
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

        for category in ServiceCategory._do_select_all_query():
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

    @staticmethod
    def _do_select_all_query() -> Iterator[dict]:
        """Query all service categories from the database"""

        for row in db.sql_query(f"SELECT id, title FROM {_CATEGORIES}"):
            yield row


class Service:
    """Wraps a service database record"""

    class NotFound(Exception):
        pass

    _bot_username: str

    def __init__(self, **kwargs):
        self._tg_id = kwargs["provider_tg_id"]
        self._category_id = kwargs["category_id"]
        self._occupation = kwargs["occupation"]
        self._description = kwargs["description"]
        self._location = kwargs["location"]
        self._is_suspended = kwargs["is_suspended"]
        self._last_modified = kwargs["last_modified"]

    def __eq__(self, other: Self):
        return self._tg_id == other._tg_id and self._category_id == other._category_id

    @property
    def category(self) -> ServiceCategory:
        return ServiceCategory.get(self._category_id)

    @property
    def provider(self) -> Provider:
        return Provider.get_by_tg_id(self._tg_id)

    @property
    def tg_id(self) -> int:
        return self._tg_id

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
        return f"t.me/{Service._bot_username}?start=service_info_{self._category_id or 0}_{self.provider.tg_username}"

    @classmethod
    def set_bot_username(cls, bot_username: str) -> None:
        Service._bot_username = bot_username

    @classmethod
    def get(cls, tg_id: int, category_id: int) -> Self:
        for row in Service._do_select_query(f"SELECT * FROM {_SERVICES} "
                                            f"WHERE provider_tg_id=? AND category_id=?", (tg_id, category_id)):
            return Service(**row)
        raise Service.NotFound

    @classmethod
    def get_all_active(cls) -> Iterator[Self]:
        for row in Service._do_select_query(f"SELECT s.* "
                                            f"FROM {_SERVICES} s, {_PROVIDERS} p "
                                            f"WHERE s.provider_tg_id=p.tg_id AND s.is_suspended=? "
                                            f"ORDER BY p.tg_username COLLATE NOCASE", (0,)):
            yield Service(**row)

    @staticmethod
    def set(tg_id: int, occupation: str, description: str, location: str, is_suspended: bool, category_id: int) -> None:
        db.sql_exec(f"INSERT OR REPLACE INTO {_SERVICES} "
                    f"(provider_tg_id, occupation, description, location, is_suspended, category_id) "
                    f"VALUES(?, ?, ?, ?, ?, ?)",
                    (tg_id, occupation, description, location, 1 if is_suspended else 0, category_id))

    @staticmethod
    def set_is_suspended(tg_id: int, category_id: int, is_suspended: bool):
        db.sql_exec(f"UPDATE {_SERVICES} SET is_suspended=? WHERE provider_tg_id=? AND category_id=?",
                    (is_suspended, tg_id, category_id))

    @staticmethod
    def delete(tg_id: int, category_id: int) -> None:
        """Delete the service record identified by `tg_id` and `category_id`"""

        db.sql_exec(f"DELETE FROM {_SERVICES} WHERE provider_tg_id=? AND category_id=?", (tg_id, category_id))

    @classmethod
    def get_all_by_user(cls, tg_id) -> Iterator[Self]:
        for row in Service._do_select_query(f"SELECT * FROM {_SERVICES} WHERE provider_tg_id=?", (tg_id,)):
            yield Service(**row)

    @classmethod
    def get_count_by_user(cls, tg_id) -> int:
        for row in db.sql_query(f"SELECT COUNT(1) AS count FROM {_SERVICES} WHERE provider_tg_id=?", (tg_id,)):
            return int(row["count"])

    @staticmethod
    def _do_select_query(query: str, params: tuple = ()) -> Iterator[dict]:
        """Select services and convert data to correct types

        @param query: SQL query to execute (supposed to be a SELECT from the services table)
        @param params: data to bind to the query

        Executes `query` with `params`.  Converts returned data to their correct types (`last_modified` to datetime and
        `is_suspended` to bool).  Data is returned as a dictionary with keys compatible with `Service.__init__()`.
        """

        for record in db.sql_query(query, params):
            record["last_modified"] = datetime.datetime.fromisoformat(record["last_modified"])
            record["is_suspended"] = bool(record["is_suspended"])
            yield record


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


def people_category_views_register(viewer_tg_id: int, category_id: int) -> None:
    """Register a single event of a user browsing a category

    @param viewer_tg_id: Telegram ID of a user that requests the information.
    @param category_id: ID of a category being viewed, -1 for the general view (no specific category was requested).
    """

    db.sql_exec("INSERT INTO services_category_views (viewer_tg_id, category_id) VALUES(?, ?)",
                (viewer_tg_id, category_id))


def people_views_register(viewer_tg_id: int, tg_id: int, category_id: int) -> None:
    """Register a single event of a user viewing a service description

    @param viewer_tg_id: Telegram ID of a user that requests the information.
    @param tg_id: Telegram ID of a user whose service is being viewed.
    @param category_id: ID of a category of the service that is being viewed.
    """

    db.sql_exec("INSERT INTO services_service_views (viewer_tg_id, tg_id, category_id) VALUES(?, ?, ?)",
                (viewer_tg_id, tg_id, category_id))


def people_category_views_report(from_date: datetime.datetime) -> Iterator[ServiceCategoryStats]:
    parameters = (from_date.strftime("%Y-%m-%d"),)
    additional_where_clause = ""
    if not settings.SERVICES_STATS_INCLUDE_ADMINISTRATORS:
        admin_id_phds = ", ".join(["?"] * len(settings.ADMINISTRATORS))
        additional_where_clause = f"AND viewer_tg_id NOT IN ({admin_id_phds})"
        parameters += tuple(admin["id"] for admin in settings.ADMINISTRATORS)
    query = (f"SELECT category_id, COUNT(1) as view_count, COUNT(DISTINCT viewer_tg_id) as viewer_count "
             f"FROM services_category_views "
             f"WHERE timestamp > ? {additional_where_clause} "
             f"GROUP BY category_id")

    for row in db.sql_query(query, parameters):
        yield ServiceCategoryStats(**row)


def export_db() -> dict:
    def all_providers() -> Iterator[dict]:
        for row in db.sql_query(f"SELECT * FROM {_PROVIDERS}"):
            yield row

    def service_select_all() -> Iterator:
        """Query all non-suspended service records from the database table"""

        for row in db.sql_query(f"SELECT * FROM {_SERVICES}"):
            yield row

    def service_category_select_all() -> Iterator:
        """Query all non-suspended service records from the database table"""

        for row in db.sql_query(f"SELECT * FROM {_CATEGORIES}"):
            yield row

    return {"categories": [category for category in service_category_select_all()],
            "providers": [provider for provider in all_providers()],
            "services": [person for person in service_select_all()]}


def import_db(new_data) -> None:
    cursor = db.cursor()

    import_timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%Z")
    categories_backup = f"services_categories_{import_timestamp}"
    providers_backup = f"services_providers_{import_timestamp}"
    services_backup = f"services_services_{import_timestamp}"

    for query in (f"CREATE TABLE {categories_backup} AS SELECT * FROM {_CATEGORIES}",
                  f"CREATE TABLE {providers_backup} AS SELECT * FROM {_PROVIDERS}",
                  f"CREATE TABLE {services_backup} AS SELECT * FROM {_SERVICES}"):
        db.sql_exec(query)

    db.commit()

    logging.info(f"Saved current data into {categories_backup}, {providers_backup} and {services_backup}")

    cursor.execute(f"DELETE FROM {_CATEGORIES}")
    for c in new_data["categories"]:
        cursor.execute(f"INSERT INTO {_CATEGORIES} (id, title) "
                       f"VALUES(?, ?)", (c["id"], c["title"]))

    cursor.execute(f"DELETE FROM {_PROVIDERS}")
    for p in new_data["providers"]:
        cursor.execute(f"INSERT INTO {_PROVIDERS} (tg_id, tg_username, next_ping) "
                       f"VALUES(?, ?, ?)", (p["tg_id"], p["tg_username"], p["next_ping"]))

    cursor.execute(f"DELETE FROM {_SERVICES}")
    for p in new_data["services"]:
        cursor.execute(
            f"INSERT INTO {_SERVICES} (tg_id, category_id, is_suspended, last_modified, occupation, "
            f"description, location) "
            f"VALUES(?, ?, ?, ?, ?, ?, ?)", (
                p["tg_id"], p["category_id"], p["is_suspended"], p["last_modified"],
                p["occupation"], p["description"], p["location"]))

    db.commit()

    logging.info("Loaded new data")

    cursor.execute(f"DROP TABLE {categories_backup}")
    cursor.execute(f"DROP TABLE {providers_backup}")
    cursor.execute(f"DROP TABLE {services_backup}")

    db.commit()

    logging.info("Dropped data snapshots")

    ServiceCategory.load()


def init():
    Provider.load()
    ServiceCategory.load()
