"""
Keyboards used in the Services feature
"""

import gettext
from collections.abc import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User

from common import i18n
from . import const, state


def standard(user: User) -> InlineKeyboardMarkup:
    """Build the standard keyboard for the `user`

    The standard keyboard is displayed at the start of the conversation (handling the /start command) or in the end of
    any conversation, and looks like this:

    +-----------------+
    | WHO             |
    +-----------------+
    | ENROLL (MORE)   |
    +--------+--------+
    | UPDATE | RETIRE |
    +--------+--------+

    Depending on the context, certain buttons can be hidden.  The enroll button is only shown when it is possible to
    add a new record.  The update and retire buttons are only shown when the user has at least one record.
    """

    trans = i18n.trans(user)

    command_buttons = {trans.gettext("SERVICES_BUTTON_WHO"): const.COMMAND_WHO,
                       trans.gettext("SERVICES_BUTTON_ENROLL"): const.COMMAND_ENROLL,
                       trans.gettext("SERVICES_BUTTON_ENROLL_MORE"): const.COMMAND_ENROLL,
                       trans.gettext("SERVICES_BUTTON_UPDATE"): const.COMMAND_UPDATE,
                       trans.gettext("SERVICES_BUTTON_RETIRE"): const.COMMAND_RETIRE}
    button_who, button_enroll, button_enroll_more, button_update, button_retire = (
        InlineKeyboardButton(text, callback_data=command) for text, command in command_buttons.items())

    buttons = [[button_who]]

    records = [r for r in state.Service.get_all_by_user(user.id)]

    if not records:
        buttons.append([button_enroll])
    elif len(records) <= state.ServiceCategory.count():
        buttons.append([button_enroll_more])

    if len(records) > 0:
        buttons.append([button_update, button_retire])

    return InlineKeyboardMarkup(buttons)


def select_category(categories: Iterable[state.ServiceCategory] = None) -> InlineKeyboardMarkup | None:
    """Build the keyboard for selecting a category

    @param categories: optional categories to show.  If not provided, the function will use the list of categories
    defined in the DB.
    @return: keyboard markup or None

    If there is at least one category, returns an instance of InlineKeyboardMarkup that contains a vertically aligned
    set of buttons:

    +------------+
    | Category 1 |
    +------------+
    | Category 2 |
    +------------+
    | ...        |
    +------------+
    | Default    |
    +------------+

    Each button has the category ID in its callback data.  Only categories defined in the DB are returned, maintaining
    their standard order.
    """

    effective_categories = categories if categories is not None else state.ServiceCategory.all()
    effective_ids = [c.id for c in effective_categories]

    buttons = [(InlineKeyboardButton(c.title, callback_data=c.id),) for c in state.ServiceCategory.all() if
               c.id in effective_ids]
    if not buttons:
        return None

    return InlineKeyboardMarkup(buttons)


def yes_no(trans: gettext.GNUTranslations) -> InlineKeyboardMarkup:
    """Build the YES/NO keyboard used in the step where the user confirms legality of their service

    +-----+----+
    | YES | NO |
    +-----+----+

    Returns an instance of InlineKeyboardMarkup.
    """

    response_buttons = {trans.gettext("SERVICES_BUTTON_YES"): const.RESPONSE_YES,
                        trans.gettext("SERVICES_BUTTON_NO"): const.RESPONSE_NO}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data=command) for text, command in
                                               response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


def approve_service_change(data: dict) -> InlineKeyboardMarkup:
    """Build the YES/NO keyboard presented to a moderator that would approve or suspend a new or updated service

    @param data: dictionary that must contain `tg_id` and `category_id` of the service to be moderated.

    Returns an instance of InlineKeyboardMarkup with Yes and No buttons aligned in a row.  Buttons have callback data
    that encodes decision and identifiers of the service.

    +-----+----+
    | YES | NO |
    +-----+----+

    """

    trans = i18n.default()

    response_buttons = {trans.gettext("SERVICES_BUTTON_YES"): const.MODERATOR_APPROVE,
                        trans.gettext("SERVICES_BUTTON_NO"): const.MODERATOR_DECLINE}
    response_button_yes, response_button_no = (
        InlineKeyboardButton(text, callback_data="{}:{}:{}".format(command, data["tg_id"], data["category_id"])) for
        text, command in response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))
