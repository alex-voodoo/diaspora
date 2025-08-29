"""
Keyboards used in the Services feature
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User

from common import db, i18n
from . import const


def standard(user: User):
    """Builds the standard keyboard for the `user`

    The standard keyboard is displayed at the start of the conversation (handling the /start command) or in the end of
    any conversation, and looks like this:

    +-----------------+
    | WHO             |
    +-----------------+
    | ENROLL (MORE)   |
    +--------+--------+
    | UPDATE | RETIRE |
    +--------+--------+

    Depending on the context, certain commands can be omitted.  The enroll button is only shown when it is possible to
    add a new record.  The update and retire buttons are only shown when the user has at least one record.

    Returns an instance of InlineKeyboardMarkup.
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

    records = [r for r in db.people_records(user.id)]
    categories = [c for c in db.people_category_select_all()]

    if not records:
        buttons.append([button_enroll] if not records else [button_enroll_more])
    elif len(records) <= len(categories):
        buttons.append([button_enroll_more])

    if len(records) > 0:
        buttons.append([button_update, button_retire])

    return InlineKeyboardMarkup(buttons)


def select_category(user: User, categories, show_other=False):
    """Builds the keyboard for selecting a category

    Categories can be provided via the optional `categories` parameter and should be an iterable of dict-like items,
    where each item should have `id` and `title` keys, holding the ID and the title of the category.

    If `categories` is None or empty, the function will load data from the DB.

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

    Each button has the category ID in its callback data.  The "Default" item means "no category", its callback data is
    set to 0.

    If no categories are defined in the DB and show_other is False, this function returns None.
    """

    trans = i18n.trans(user)

    buttons = []
    added_other = False
    for category in categories if categories else db.people_category_select_all():
        buttons.append((InlineKeyboardButton(
            category["title"] if category["title"] else trans.gettext("SERVICES_BUTTON_ENROLL_CATEGORY_DEFAULT"),
            callback_data=category["id"] if category["id"] else 0),))
        if not category["id"]:
            added_other = True
    if show_other and not added_other:
        buttons.append(
            (InlineKeyboardButton(trans.gettext("SERVICES_BUTTON_ENROLL_CATEGORY_DEFAULT"), callback_data=0),))
    if not buttons:
        return None
    return InlineKeyboardMarkup(buttons)


def yes_no(user: User) -> InlineKeyboardMarkup:
    """Builds the YES/NO keyboard used in the step where the user confirms legality of their service

    +-----+----+
    | YES | NO |
    +-----+----+

    Returns an instance of InlineKeyboardMarkup.
    """

    trans = i18n.trans(user)

    response_buttons = {trans.gettext("SERVICES_BUTTON_YES"): const.RESPONSE_YES,
                        trans.gettext("SERVICES_BUTTON_NO"): const.RESPONSE_NO}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data=command) for text, command in
                                               response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


def approve_service_change(data) -> InlineKeyboardMarkup:
    trans = i18n.default()

    response_buttons = {trans.gettext("SERVICES_BUTTON_YES"): const.MODERATOR_APPROVE,
                        trans.gettext("SERVICES_BUTTON_NO"): const.MODERATOR_DECLINE}
    response_button_yes, response_button_no = (
        InlineKeyboardButton(text, callback_data="{}:{}:{}".format(command, data["tg_id"], data["category_id"])) for
        text, command in response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))
