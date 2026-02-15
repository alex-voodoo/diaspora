from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User

from common import i18n
from features.moderation import const, render


def select_complaint_reason(user: User, original_message_id: int) -> InlineKeyboardMarkup:
    """Build the keyboard for selecting a reason for sending a moderation request

    Returns an instance of InlineKeyboardMarkup that contains a vertically aligned set of reasons:

    +----------+
    | Reason 1 |
    +----------+
    | Reason 2 |
    +----------+
    | ...      |
    +----------+

    Each button has the reason ID in its callback data.
    """

    trans = i18n.trans(user)

    buttons = [(InlineKeyboardButton(render.reason_title(trans, reason_id),
                                     callback_data=f"{original_message_id}:{user.id}:{reason_id}"),) for reason_id in
               range(const.MODERATION_REASON_COUNT)]
    return InlineKeyboardMarkup(buttons)
