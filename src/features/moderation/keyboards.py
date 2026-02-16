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
    | Cancel   |
    +----------+

    Each button has three numeric IDs packed in its callback data.  See `unpack_complaint_reason()` for the details.
    """

    trans = i18n.trans(user)

    buttons = [(InlineKeyboardButton(render.reason_title(trans, reason_id),
                                     callback_data=f"{original_message_id}:{user.id}:{reason_id}"),) for reason_id in
               range(const.MODERATION_REASON_COUNT)]
    buttons.append((InlineKeyboardButton(render.reason_title(trans, const.MODERATION_REASON_CANCEL),
                                         callback_data=f"0:0:{const.MODERATION_REASON_CANCEL}"),))
    return InlineKeyboardMarkup(buttons)


def unpack_complaint_reason(query_data: str) -> tuple[int, int, int]:
    """Unpack data sent in a callback query by pressing a button in a keyboard created by `select_complain_reason()`

    @param query_data: string attached to a button
    @return: tuple that consists three items: ID of the original message, ID of the user that pressed the button, and
    ID of the complaint reason.  The latter may be `const.MODERATION_REASON_CANCEL`, in that case two other IDs will be
    equal to zero.
    """

    original_message_id, from_user_id, reason_id = (int(x) for x in query_data.split(":"))
    return original_message_id, from_user_id, reason_id
