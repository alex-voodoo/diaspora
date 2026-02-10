"""
Persistent state of the moderation feature
"""

import datetime
import pickle
from typing import Self

from telegram import Message
from telegram.constants import MessageOriginType

from common import db, util
from common.settings import settings
from . import const

# Root dictionaries in the state
_COMPLAINTS, _POLLS = "complaints", "polls"

_STATE_FILENAME = settings.data_dir / "moderation_state.pkl"

# State object.  Loaded once from the file, then used in-memory, saved to the file when changed.
_state = {}


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
            "INSERT OR REPLACE INTO moderation_main_chat_messages (tg_id, timestamp, text, sender_tg_id, sender_name, "
            "sender_username) "
            "VALUES(?, ?, ?, ?, ?, ?)", (
                message.id, message.date.strftime("%Y-%m-%d %H:%M:%S"), message.text, message.from_user.id,
                message.from_user.full_name, message.from_user.username))

    @classmethod
    def find_original(cls, forwarded_message: Message) -> Self | None:
        if forwarded_message.forward_origin.type == MessageOriginType.USER:
            where_clause = "sender_tg_id=?"
            where_params = (forwarded_message.forward_origin.sender_user.id,)
        elif forwarded_message.forward_origin.type == MessageOriginType.HIDDEN_USER:
            where_clause = "sender_name=?"
            where_params = (forwarded_message.forward_origin.sender_user_name,)
        else:
            raise RuntimeError(f"Unsupported forward origin: {forwarded_message.forward_origin.type}")

        for row in db.sql_query(f"SELECT * FROM moderation_main_chat_messages "
                                f"WHERE timestamp=? AND text=? AND {where_clause} ",
                                (util.db_format(forwarded_message.forward_origin.date),
                                 forwarded_message.text) + where_params):
            row["timestamp"] = datetime.datetime.fromisoformat(row["timestamp"])
            original_message = MainChatMessage(**row)
            return original_message
        return None

    @classmethod
    def get(cls, tg_id: int) -> Self:
        for row in db.sql_query("SELECT * FROM moderation_main_chat_messages WHERE tg_id=?", (tg_id,)):
            return MainChatMessage(**row)
        raise MainChatMessage.NotFound


class Complaint:
    """Accumulates moderation requests about a single message in the main chat

    Complaints are stored in the state in a dictionary where keys are IDs of the original messages.
    """

    def __init__(self, violator_id):
        # Telegram ID of the original poster of the message that the complaint is raised for.
        self._violator_id = violator_id
        # Telegram IDs of users that complained about this message.
        self._users = set()
        # Reasons that users specified when sending their complaints.
        self._reasons = dict()
        # ID of the moderation poll created when this complaint accumulates enough requests.
        self.poll_id = ""
        # Whether this complaint accepts new requests.
        self._is_open = True

    def has_user(self, user_id) -> bool:
        """Return whether this complaint has a request from the given user"""

        return user_id in self._users

    def maybe_add_reason(self, from_user_id: int, reason: int) -> bool:
        """Register a request from the given user, but only if there was no earlier request from that user

        Returns whether the request was registered.
        """

        if self.has_user(from_user_id):
            return False
        self._users.add(from_user_id)

        if reason not in self._reasons:
            self._reasons[reason] = 0
        self._reasons[reason] = self._reasons[reason] + 1
        return True

    @property
    def count(self) -> int:
        """Return how many requests are registered in this complaint"""

        return sum(self._reasons.values())

    @property
    def reasons(self) -> dict:
        return self._reasons

    @property
    def is_open(self) -> bool:
        """Return whether this complaint accepts requests"""

        return self._is_open

    def close(self) -> None:
        self._is_open = False


class Poll:
    """Links together a poll, a message that the poll is contained in, and an original message that the poll is about"""

    def __init__(self, original_message_id, poll_message_id):
        self.original_message_id = original_message_id
        self.poll_message_id = poll_message_id


class Restriction:
    """Explains current restriction put on a user
    """

    def __init__(self, tg_id: int, level: int, until_timestamp: datetime.datetime,
                 cooldown_until_timestamp: datetime.datetime):
        self._tg_id = tg_id
        self._level = level
        self._until_timestamp = until_timestamp
        self._cooldown_until_timestamp = cooldown_until_timestamp

    @property
    def level(self):
        return self._level

    @property
    def until_timestamp(self) -> datetime.datetime:
        return self._until_timestamp

    @property
    def cooldown_until_timestamp(self):
        return self._cooldown_until_timestamp

    @classmethod
    def _construct_from_row(cls, row: dict) -> Self:
        row["until_timestamp"] = datetime.datetime.fromisoformat(row["until_timestamp"])
        row["cooldown_until_timestamp"] = datetime.datetime.fromisoformat(row["cooldown_until_timestamp"])
        return Restriction(**row)

    @classmethod
    def get_or_create(cls, tg_id: int) -> Self:
        for row in db.sql_query("SELECT * "
                                "FROM moderation_restrictions "
                                "WHERE tg_id=? AND cooldown_until_timestamp>DATETIME('now')", (tg_id,)):
            return cls._construct_from_row(row)
        past_timestamp = util.rounded_now() - datetime.timedelta(seconds=1)
        return Restriction(tg_id, -1, past_timestamp, past_timestamp + datetime.timedelta(days=1))

    @classmethod
    def get_most_recent(cls, tg_id) -> Self | None:
        for row in db.sql_query("SELECT * "
                                "FROM moderation_restrictions "
                                "WHERE tg_id=? "
                                "ORDER BY cooldown_until_timestamp DESC", (tg_id,)):
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

        db.sql_exec("DELETE FROM moderation_restrictions WHERE tg_id=? AND cooldown_until_timestamp>DATETIME('now')",
                    (restriction._tg_id,))
        db.sql_exec("INSERT INTO moderation_restrictions(tg_id, level, until_timestamp, cooldown_until_timestamp) "
                    "VALUES(?, ?, ?, ?)",
                    (restriction._tg_id, new_level, util.db_format(new_until_timestamp),
                     util.db_format(new_cooldown_until_timestamp)))

        return Restriction(restriction._tg_id, new_level, new_until_timestamp, new_cooldown_until_timestamp)


def _save() -> None:
    with open(_STATE_FILENAME, "wb") as out_pickle:
        pickle.dump(_state, out_pickle, pickle.HIGHEST_PROTOCOL)


def complaint_get(original_message: MainChatMessage) -> Complaint:
    """Get a complaint created for the original message with the given ID, create a new complaint if there is none"""

    global _state

    complaints = _state[_COMPLAINTS]

    if original_message.tg_id not in complaints:
        complaints[original_message.tg_id] = Complaint(original_message.sender_tg_id)

    _save()

    return complaints[original_message.tg_id]


def complaint_maybe_add(original_message_id: int, from_user_id: int, reason: int) -> Complaint:
    """Try to register a new moderation request from a user

    Forwards parameters to `Complaint.maybe_add_reason()` of a complaint created for the original message with the given
    ID.  Returns the complaint.
    """

    global _state

    complaints = _state[_COMPLAINTS]

    complaint = complaints[original_message_id]
    complaint.maybe_add_reason(from_user_id, reason)

    _save()

    return complaint


def poll_register(original_message_id: int, poll_message_id: int, poll_id: str) -> None:
    """Register a new poll for the original message with the given ID"""

    global _state

    polls = _state[_POLLS]
    assert poll_id not in polls
    polls[poll_id] = Poll(original_message_id, poll_message_id)

    _state[_COMPLAINTS][original_message_id].poll_id = poll_id

    _save()


def poll_get(poll_id: str) -> Poll:
    """Return a poll with the given ID"""

    return _state[_POLLS][poll_id]


def clean(original_message_id: int) -> None:
    """Remove complaint and poll data (if any) associated with the original message with the given ID"""

    global _state

    complaint = _state[_COMPLAINTS][original_message_id]
    _state[_POLLS].pop(complaint.poll_id)
    _state[_COMPLAINTS].pop(original_message_id)

    _save()


def init() -> None:
    global _state

    MainChatMessage.maybe_delete_old_messages()

    if _state:
        return

    try:
        with open(_STATE_FILENAME, "rb") as inp:
            _state = pickle.load(inp)
    except FileNotFoundError:
        # First run, no problem, create an empty state.
        _state = {}

    if _COMPLAINTS not in _state or not settings.MODERATION_IS_REAL:
        _state[_COMPLAINTS] = dict()
    if _POLLS not in _state or not settings.MODERATION_IS_REAL:
        _state[_POLLS] = dict()
