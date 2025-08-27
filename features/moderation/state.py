"""
Persistent state of the moderation feature
"""

import pathlib
import pickle

from telegram import Message

# Root dictionaries in the state
_COMPLAINTS, _MAIN_CHAT_LOG, _POLLS = "complaints", "main_chat_log", "polls"

_STATE_FILENAME = pathlib.Path(__file__).parent.parent / "resources" / "moderation_state.pkl"

# State object.  Loaded once from the file, then used in-memory, saved to the file when changed.
_state = {}


class Complaint:
    """Accumulates moderation requests about a single message in the main chat"""

    def __init__(self):
        self._users = set()
        self._reasons = dict()
        self.poll_id = ""

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


class Poll:
    """Links together a poll, a message that the poll is contained in, and an original message that the poll is about"""

    def __init__(self, original_message_id, poll_message_id):
        self.original_message_id = original_message_id
        self.poll_message_id = poll_message_id


def _save() -> None:
    with open(_STATE_FILENAME, "wb") as out_pickle:
        pickle.dump(_state, out_pickle, pickle.HIGHEST_PROTOCOL)


def main_chat_log_add_or_update(message: Message) -> None:
    """Store a new or edited message that came to the main chat"""

    global _state

    log = _state[_MAIN_CHAT_LOG]

    log[message.id] = message

    _save()


def main_chat_log_find(text: str) -> int:
    """Return ID of a message that contains `text`, or 0 if no such message"""

    for message in _state[_MAIN_CHAT_LOG].values():
        if message.text == text:
            return message.id

    return 0


def complaint_get(original_message_id: int) -> Complaint:
    """Get a complaint created for the original message with the given ID, create a new complaint if there is none"""

    global _state

    complaints = _state[_COMPLAINTS]

    if original_message_id not in complaints:
        complaints[original_message_id] = Complaint()

    _save()

    return complaints[original_message_id]


def complaint_maybe_add(original_message_id: int, from_user_id: int, reason: int) -> Complaint:
    """Try to register a new moderation request from a user

    Forwards parameters to `Complaint.maybe_add_reason()` of a complaint created for the original message with the given
    ID.  Returns the complaint.
    """

    global _state

    complaint = complaint_get(original_message_id)
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

    complaint = complaint_get(original_message_id)
    _state[_POLLS].pop(complaint.poll_id)
    _state[_COMPLAINTS].pop(original_message_id)

    _save()


def init() -> None:
    global _state

    if _state:
        return

    try:
        with open(_STATE_FILENAME, "rb") as inp:
            _state = pickle.load(inp)
    except FileNotFoundError:
        # First run, no problem, create an empty state.
        _state = {}

    if _MAIN_CHAT_LOG not in _state:
        _state[_MAIN_CHAT_LOG] = dict()
    if _COMPLAINTS not in _state:
        _state[_COMPLAINTS] = dict()
    if _POLLS not in _state:
        _state[_POLLS] = dict()

    # TODO: remove the below when this feature passes alpha testing.
    _state[_COMPLAINTS] = dict()
    _state[_POLLS] = dict()
