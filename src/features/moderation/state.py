"""
Persistent state of the moderation feature
"""

import datetime
from collections.abc import Iterator
from typing import Self

from telegram import Message, MessageOriginHiddenUser, MessageOriginUser
from telegram.constants import MessageOriginType

from common import db, util
from common.settings import settings
from . import const


class ComplaintReason:
    """Wraps a moderation complaint reason database record

    The class caches the entire `moderation_complaint_reasons` table and provides methods for accessing individual items
    and the entire collection.

    The storage must be initialised by calling the `load()` class method.
    """

    _reasons = {}
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
        """Get a moderation complaint reason identified by `db_id`

        Raises `KeyError` if no object found for the given ID.
        """

        return cls._reasons[db_id]

    @classmethod
    def load(cls) -> None:
        """Load all service category records from the DB and store them in a class attribute"""

        cls._reasons = {}

        for row in db.sql_query("SELECT * FROM moderation_complaint_reasons"):
            cls._reasons[row["id"]] = ComplaintReason(**row)

        cls._order = [c.id for c in sorted(cls._reasons.values(), key=lambda v: v.title)]

    @classmethod
    def count(cls) -> int:
        """Return number of reasons"""

        return len(cls._reasons)

    @classmethod
    def all(cls) -> Iterator[Self]:
        """Return all reasons sorted alphabetically by title"""

        for db_id in cls._order:
            yield cls.get(db_id)


class MainChatMessage:
    class NotFound(Exception):
        pass

    _next_cleanup_timestamp = datetime.datetime.now() - datetime.timedelta(seconds=1)

    def __init__(self, tg_id: int, timestamp: datetime, text: str, sender_tg_id: int, sender_name: str,
                 sender_username: str):
        self._tg_id = tg_id
        self._timestamp = timestamp
        self._text = text
        self._sender_tg_id = sender_tg_id
        self._sender_name = sender_name
        self._sender_username = sender_username

    @property
    def tg_id(self) -> int:
        return self._tg_id

    @property
    def timestamp(self) -> datetime.datetime:
        return self._timestamp

    @property
    def sender_tg_id(self) -> int:
        return self._sender_tg_id

    @classmethod
    def maybe_delete_old_messages(cls) -> None:
        if datetime.datetime.now() < cls._next_cleanup_timestamp:
            return

        oldest_timestamp_str = util.db_format(util.rounded_now() - datetime.timedelta(
            hours=settings.MODERATION_MAIN_CHAT_LOG_MAX_AGE_HOURS))
        db.sql_exec("DELETE FROM moderation_main_chat_messages WHERE timestamp<?", (oldest_timestamp_str,))

        cls._next_cleanup_timestamp = datetime.datetime.now() + datetime.timedelta(hours=1)

    @classmethod
    def log(cls, message: Message) -> None:
        db.sql_exec(
            "INSERT OR REPLACE INTO moderation_main_chat_messages "
            "(tg_id, timestamp, text, sender_tg_id, sender_name, sender_username) "
            "VALUES(?, ?, ?, ?, ?, ?)", (
                message.id, message.date.strftime("%Y-%m-%d %H:%M:%S"), cls._text_from_message(message),
                message.from_user.id,
                message.from_user.full_name, message.from_user.username))

    @classmethod
    def find_original(cls, forwarded_message: Message) -> Self | None:
        if forwarded_message.forward_origin.type == MessageOriginType.USER:
            assert isinstance(forwarded_message.forward_origin, MessageOriginUser)
            where_clause = "sender_tg_id=?"
            where_params = (forwarded_message.forward_origin.sender_user.id,)
        elif forwarded_message.forward_origin.type == MessageOriginType.HIDDEN_USER:
            assert isinstance(forwarded_message.forward_origin, MessageOriginHiddenUser)
            where_clause = "sender_name=?"
            where_params = (forwarded_message.forward_origin.sender_user_name,)
        else:
            raise RuntimeError(f"Unsupported forward origin: {forwarded_message.forward_origin.type}")

        for row in db.sql_query(f"SELECT * FROM moderation_main_chat_messages "
                                f"WHERE timestamp=? AND text=? AND {where_clause} ",
                                (util.db_format(forwarded_message.forward_origin.date),
                                 cls._text_from_message(forwarded_message)) + where_params):
            row["timestamp"] = datetime.datetime.fromisoformat(row["timestamp"])
            original_message = MainChatMessage(**row)
            return original_message
        return None

    @classmethod
    def get(cls, tg_id: int) -> Self:
        for row in db.sql_query("SELECT * FROM moderation_main_chat_messages WHERE tg_id=?", (tg_id,)):
            return MainChatMessage(**row)
        raise MainChatMessage.NotFound

    @classmethod
    def _text_from_message(cls, message: Message) -> str:
        if message.text:
            return message.text
        if message.photo:
            return ",".join(sorted(ps.file_unique_id for ps in message.photo))


class Request:
    """Moderation request that comes from a user"""

    @classmethod
    def exists(cls, original_message_tg_id: int, from_user_tg_id: int) -> bool:
        """Return whether there is a request to moderate a message from a user"""

        for _row in db.sql_query("SELECT * FROM moderation_requests "
                                 "WHERE original_message_tg_id=? AND from_user_tg_id=?",
                                 (original_message_tg_id, from_user_tg_id)):
            return True
        return False

    @classmethod
    def register(cls, original_message_tg_id: int, complaint_reason_id: int, from_user_tg_id: int) -> None:
        """Register a new request to moderate a message"""

        db.sql_exec("INSERT INTO moderation_requests(original_message_tg_id, complaint_reason_id, from_user_tg_id) "
                    "VALUES(?, ?, ?)", (original_message_tg_id, complaint_reason_id, from_user_tg_id))

    @classmethod
    def count(cls, original_message_tg_id: int) -> int:
        """Return how many requests to moderate a message has"""

        for row in db.sql_query("SELECT COUNT(1) as request_count FROM moderation_requests "
                                "WHERE original_message_tg_id=?", (original_message_tg_id,)):
            return int(row["request_count"])

    @classmethod
    def get_grouped(cls, original_message_tg_id: int) -> Iterator[tuple]:
        """Get all requests to moderate a message grouped and counted by reasons"""

        for row in db.sql_query("SELECT complaint_reason_id, COUNT(1) AS request_count FROM moderation_requests "
                                "WHERE original_message_tg_id=? "
                                "GROUP BY complaint_reason_id", (original_message_tg_id,)):
            yield row["complaint_reason_id"], row["request_count"]


class Poll:
    """Links together a poll, a message that the poll is contained in, and an original message that the poll is about"""

    class NotFound(Exception):
        pass

    def __init__(self, tg_id: str, original_message_tg_id: int, poll_message_tg_id: int, is_running: bool):
        self._tg_id = tg_id
        self._original_message_tg_id = original_message_tg_id
        self._poll_message_tg_id = poll_message_tg_id
        self._is_running = is_running

    @property
    def tg_id(self) -> str:
        return self._tg_id

    @property
    def original_message_tg_id(self) -> int:
        return self._original_message_tg_id

    @property
    def poll_message_tg_id(self) -> int:
        return self._poll_message_tg_id

    @property
    def is_running(self) -> bool:
        return self._is_running

    def stop(self) -> None:
        db.sql_exec("UPDATE moderation_polls SET is_running=0 WHERE tg_id=?", (self._tg_id,))
        self._is_running = False

    @classmethod
    def exists(cls, original_message_tg_id: int) -> bool:
        for _row in db.sql_query("SELECT * FROM moderation_polls WHERE original_message_tg_id=?",
                                 (original_message_tg_id,)):
            return True
        return False

    @classmethod
    def create(cls, tg_id: str, original_message_tg_id: int, poll_message_tg_id: int) -> None:
        db.sql_exec("INSERT INTO moderation_polls(tg_id, original_message_tg_id, poll_message_tg_id) "
                    "VALUES(?, ?, ?)", (tg_id, original_message_tg_id, poll_message_tg_id))

    @classmethod
    def get(cls, tg_id: str) -> Self:
        for row in db.sql_query("SELECT * FROM moderation_polls WHERE tg_id=?", (tg_id,)):
            row["is_running"] = bool(row["is_running"])
            return Poll(**row)
        raise cls.NotFound

    @classmethod
    def get_all_running_for(cls, user_tg_id: int) -> Iterator[Self]:
        """Return all polls running for messages sent by the same user as this one"""

        for row in db.sql_query(
                "SELECT mp.* "
                "FROM moderation_polls mp, moderation_main_chat_messages mmcm "
                "WHERE mp.original_message_tg_id=mmcm.tg_id AND mp.is_running=1 AND mmcm.sender_tg_id=?",
                (user_tg_id,)):
            yield Poll(**row)


class Restriction:
    """A restriction put on a user"""

    def __init__(self, user_tg_id: int, level: int, until_timestamp: datetime.datetime,
                 cooldown_until_timestamp: datetime.datetime):
        self._user_tg_id = user_tg_id
        self._level = level
        self._until_timestamp = until_timestamp
        self._cooldown_until_timestamp = cooldown_until_timestamp

    @property
    def level(self) -> int:
        return self._level

    @property
    def until_timestamp(self) -> datetime.datetime:
        return self._until_timestamp

    @property
    def cooldown_until_timestamp(self) -> datetime.datetime:
        return self._cooldown_until_timestamp

    @classmethod
    def _construct_from_row(cls, row: dict) -> Self:
        row["until_timestamp"] = datetime.datetime.fromisoformat(row["until_timestamp"])
        row["cooldown_until_timestamp"] = datetime.datetime.fromisoformat(row["cooldown_until_timestamp"])
        return Restriction(**row)

    @classmethod
    def get_current_or_create(cls, user_tg_id: int) -> Self:
        for row in db.sql_query("SELECT * "
                                "FROM moderation_restrictions "
                                "WHERE user_tg_id=? AND cooldown_until_timestamp>?",
                                (user_tg_id, util.db_format(util.rounded_now()))):
            return cls._construct_from_row(row)
        past_timestamp = util.rounded_now() - datetime.timedelta(seconds=1)
        return Restriction(user_tg_id, -1, past_timestamp, past_timestamp + datetime.timedelta(days=1))

    @classmethod
    def get_most_recent(cls, user_tg_id) -> Self | None:
        for row in db.sql_query("SELECT * "
                                "FROM moderation_restrictions "
                                "WHERE user_tg_id=? "
                                "ORDER BY cooldown_until_timestamp DESC", (user_tg_id,)):
            return cls._construct_from_row(row)
        return None

    @classmethod
    def elevate_or_prolong(cls, restriction: Self) -> Self:
        """Update the restriction as per the configured ladder

        @param restriction: the existing restriction
        @return: new restriction
        """

        now = util.rounded_now()
        if now < restriction.until_timestamp:
            raise RuntimeError("Restriction is still active, cannot elevate")
        if now > restriction.cooldown_until_timestamp:
            raise RuntimeError("Restriction is already gone and cooled down, cannot elevate")

        new_level = restriction.level
        if new_level < len(settings.MODERATION_RESTRICTION_LADDER) - 1:
            new_level += 1

        if new_level not in range(len(settings.MODERATION_RESTRICTION_LADDER)):
            raise RuntimeError(f"New level {new_level} is out of the configured ladder of restrictions")

        pattern = settings.MODERATION_RESTRICTION_LADDER[new_level]
        action = pattern["action"]
        if action == const.ACTION_WARN:
            new_until_timestamp = now
            new_cooldown_until_timestamp = new_until_timestamp + datetime.timedelta(minutes=pattern["cooldown"])
        elif action == const.ACTION_RESTRICT:
            new_until_timestamp = now + datetime.timedelta(minutes=pattern["duration"])
            new_cooldown_until_timestamp = new_until_timestamp + datetime.timedelta(minutes=pattern["cooldown"])
        elif action == const.ACTION_BAN:
            new_until_timestamp = now + datetime.timedelta(days=36500)
            new_cooldown_until_timestamp = new_until_timestamp
        else:
            raise RuntimeError(f"Unknown action: {action}")

        db.sql_exec("DELETE FROM moderation_restrictions "
                    "WHERE user_tg_id=? AND cooldown_until_timestamp>?",
                    (restriction._user_tg_id, util.db_format(util.rounded_now())))
        db.sql_exec("INSERT INTO moderation_restrictions(user_tg_id, level, until_timestamp, cooldown_until_timestamp) "
                    "VALUES(?, ?, ?, ?)",
                    (restriction._user_tg_id, new_level, util.db_format(new_until_timestamp),
                     util.db_format(new_cooldown_until_timestamp)))

        return Restriction(restriction._user_tg_id, new_level, new_until_timestamp, new_cooldown_until_timestamp)


def init() -> None:
    MainChatMessage.maybe_delete_old_messages()
