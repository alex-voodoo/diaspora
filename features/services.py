"""
Registry of services
"""
import copy
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

import settings
from common import i18n, db

# Commands, sequences, and responses
COMMAND_WHO, COMMAND_ENROLL, COMMAND_UPDATE, COMMAND_RETIRE = ("who", "update", "enroll", "retire")
SELECTING_CATEGORY, TYPING_OCCUPATION, TYPING_LOCATION, CONFIRMING_LEGALITY = range(4)
RESPONSE_YES, RESPONSE_NO = ("yes", "no")
MODERATOR_APPROVE, MODERATOR_DECLINE = ("approve", "decline")


def get_standard_keyboard(user: User):
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

    command_buttons = {trans.gettext("BUTTON_WHO"): COMMAND_WHO, trans.gettext("BUTTON_ENROLL"): COMMAND_ENROLL,
                       trans.gettext("BUTTON_ENROLL_MORE"): COMMAND_ENROLL,
                       trans.gettext("BUTTON_UPDATE"): COMMAND_UPDATE, trans.gettext("BUTTON_RETIRE"): COMMAND_RETIRE}
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


def get_category_keyboard(user: User, categories=None):
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

    If no categories are defined in the DB, this function returns None.
    """

    trans = i18n.trans(user)

    buttons = []
    for category in categories if categories else db.people_category_select_all():
        buttons.append((InlineKeyboardButton(
            category["title"] if category["title"] else trans.gettext("BUTTON_ENROLL_CATEGORY_DEFAULT"),
            callback_data=category["id"] if category["id"] else 0),))
    if not buttons:
        return None
    if not categories:
        buttons.append((InlineKeyboardButton(trans.gettext("BUTTON_ENROLL_CATEGORY_DEFAULT"), callback_data=0),))
    return InlineKeyboardMarkup(buttons)


def get_yesno_keyboard(user: User) -> InlineKeyboardMarkup:
    """Builds the YES/NO keyboard used in the step where the user confirms legality of their service

    +-----+----+
    | YES | NO |
    +-----+----+

    Returns an instance of InlineKeyboardMarkup.
    """

    trans = i18n.trans(user)

    response_buttons = {trans.gettext("BUTTON_YES"): RESPONSE_YES, trans.gettext("BUTTON_NO"): RESPONSE_NO}
    response_button_yes, response_button_no = (InlineKeyboardButton(text, callback_data=command) for text, command in
                                               response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


def get_moderation_keyboard(data) -> InlineKeyboardMarkup:
    trans = i18n.default()

    response_buttons = {trans.gettext("BUTTON_YES"): MODERATOR_APPROVE, trans.gettext("BUTTON_NO"): MODERATOR_DECLINE}
    response_button_yes, response_button_no = (
        InlineKeyboardButton(text, callback_data="{}:{}:{}".format(command, data["tg_id"], data["category_id"])) for
        text, command in response_buttons.items())

    return InlineKeyboardMarkup(((response_button_yes, response_button_no),))


async def show_main_status(context: ContextTypes.DEFAULT_TYPE, message: Message, user: User,
                           prefix="") -> None:
    """Show the current status of the user"""

    records = [r for r in db.people_records(user.id)]

    trans = i18n.trans(user)

    if records:
        logging.info("This is {username} that has records already".format(username=user.username))

        def get_header():
            if len(records) == 1:
                return trans.gettext("MESSAGE_DM_HELLO_AGAIN {user_first_name}").format(user_first_name=user.first_name)
            return trans.ngettext("MESSAGE_DM_HELLO_AGAIN_S {user_first_name} {record_count}",
                                  "MESSAGE_DM_HELLO_AGAIN_P {user_first_name} {record_count}", len(records)).format(
                user_first_name=user.first_name, record_count=len(records))

        text = []
        if prefix:
            text.append(prefix)
        text.append(get_header())

        for record in records:
            text.append("<b>{c}:</b> {o} ({l})".format(
                c=record["title"] if record["title"] else trans.gettext("BUTTON_ENROLL_CATEGORY_DEFAULT"),
                o=record["occupation"], l=record["location"]))

        await message.reply_text("\n".join(text), reply_markup=get_standard_keyboard(user))
    else:
        logging.info("Welcoming user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

        if prefix:
            text = prefix + "\n" + trans.gettext("MESSAGE_DM_NO_RECORDS")
        else:
            main_chat = await context.bot.get_chat(settings.MAIN_CHAT_ID)

            text = trans.gettext("MESSAGE_DM_HELLO {bot_first_name} {main_chat_name}").format(
                bot_first_name=context.bot.first_name, main_chat_name=main_chat.title)

        await message.reply_text(text, reply_markup=get_standard_keyboard(user))


# noinspection PyUnusedLocal
async def moderate_new_data(update: Update, context: ContextTypes.DEFAULT_TYPE, data) -> None:
    moderator_ids = settings.ADMINISTRATORS.keys() if settings.ADMINISTRATORS else (settings.DEVELOPER_CHAT_ID,)

    for moderator_id in moderator_ids:
        logging.info("Sending moderation request to moderator ID {id}".format(id=moderator_id))
        await context.bot.send_message(chat_id=moderator_id,
                                       text=i18n.default().gettext("MESSAGE_ADMIN_APPROVE_USER_DATA {username}").format(
                                           username=data["tg_username"], occupation=data["occupation"],
                                           location=data["location"]), reply_markup=get_moderation_keyboard(data))


# noinspection PyUnusedLocal
def who_people_to_message(people: list) -> list:
    result = []
    for p in people:
        result.append(
            "@{username} ({location}): {occupation}".format(username=p["tg_username"], occupation=p["occupation"],
                                                            location=p["location"]))
    return result


async def who_request_category(update: Update, context: ContextTypes.DEFAULT_TYPE, filtered_people: list) -> int:
    """Ask user for a category to show"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    category_list = []

    for c in filtered_people:
        category_list.append(
            {"id": c["category_id"], "title": c["title"], "text": "{t}: {c}".format(t=c["title"], c=len(c["people"]))})

    await query.message.reply_text(i18n.trans(query.from_user).gettext("MESSAGE_DM_WHO_CATEGORY_LIST").format(
        categories="\n".join([c["text"] for c in category_list])),
        reply_markup=get_category_keyboard(query.from_user, category_list))

    context.user_data["who_request_category"] = filtered_people

    return SELECTING_CATEGORY


async def who_received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List users in the category that the user selected previously"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    filtered_people = context.user_data["who_request_category"]

    category = None
    for c in filtered_people:
        if c["category_id"] == int(query.data):
            category = c
            break
    if not category:
        await query.message.reply_text(text=i18n.trans(query.from_user).gettext("MESSAGE_DM_WHO_CATEGORY_EMPTY"),
                                       reply_markup=get_standard_keyboard(query.from_user))
        return ConversationHandler.END

    user_list = ["<b>{t}</b>".format(t=category["title"])] + who_people_to_message(category["people"])

    await query.message.reply_text(text="\n".join(user_list), reply_markup=get_standard_keyboard(query.from_user))

    del context.user_data["who_request_category"]
    return ConversationHandler.END


# noinspection PyUnusedLocal
async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the current registry"""

    query = update.callback_query

    await query.answer()

    trans = i18n.trans(query.from_user)

    user_list = [trans.gettext("MESSAGE_DM_WHO_LIST_HEADING")]

    categorised_people = {
        0: {"title": trans.gettext("MESSAGE_DM_WHO_CATEGORY_DEFAULT"), "category_id": 0, "people": []}}

    for category in db.people_category_select_all():
        categorised_people[category["id"]] = {"title": category["title"], "people": []}

    for person in db.people_select_all():
        if "category_id" not in person or person["category_id"] not in categorised_people:
            person["category_id"] = 0
        categorised_people[person["category_id"]]["people"].append(person)

    filtered_people = [{"title": c["title"], "category_id": i, "people": c["people"]} for i, c in
                       categorised_people.items() if i != 0 and c["people"]]
    if categorised_people[0]["people"]:
        filtered_people.append(categorised_people[0])

    if settings.SHOW_CATEGORIES_ALWAYS and len(filtered_people) > 1:
        return await who_request_category(update, context, filtered_people)
    else:
        if len(filtered_people) == 1:
            user_list += who_people_to_message(filtered_people[0]["people"])
        else:
            for category in filtered_people:
                user_list.append("")
                user_list.append("<b>{t}</b>".format(t=category["title"]))
                user_list += who_people_to_message(category["people"])

        if len(user_list) == 1:
            user_list = [trans.gettext("MESSAGE_DM_WHO_EMPTY")]

        united_message = "\n".join(user_list)
        if len(united_message) < settings.MAX_MESSAGE_LENGTH:
            await query.edit_message_reply_markup(None)
            await query.message.reply_text(text=united_message, reply_markup=get_standard_keyboard(query.from_user))
            return ConversationHandler.END
        else:
            return await who_request_category(update, context, filtered_people)


# noinspection PyUnusedLocal
async def enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about adding the first user record"""

    query = update.callback_query

    trans = i18n.trans(query.from_user)

    await query.answer()
    await query.edit_message_reply_markup(None)

    if not query.from_user.username:
        await query.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_USERNAME_REQUIRED"),
                                       reply_markup=get_standard_keyboard(query.from_user))
        return ConversationHandler.END

    await query.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_START"))

    existing_category_ids = [r["id"] for r in db.people_records(query.from_user.id)]
    categories = [c for c in db.people_category_select_all() if c["id"] not in existing_category_ids]

    category_buttons = get_category_keyboard(query.from_user, categories)

    if category_buttons:
        await query.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_ASK_CATEGORY"), reply_markup=category_buttons)

        return SELECTING_CATEGORY
    else:
        user_data = context.user_data
        user_data["category_id"] = 0

        await query.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_ASK_OCCUPATION"))

        return TYPING_OCCUPATION


# noinspection PyUnusedLocal
async def handle_command_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about updating an existing user record"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(i18n.trans(query.from_user).gettext("MESSAGE_DM_SELECT_CATEGORY_FOR_UPDATE"),
                                   reply_markup=get_category_keyboard(query.from_user,
                                                                      db.people_records(query.from_user.id)))

    context.user_data["mode"] = "update"

    return SELECTING_CATEGORY


async def received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    query = update.callback_query

    trans = i18n.trans(query.from_user)

    user_data = context.user_data
    user_data["category_id"] = query.data

    await query.answer()
    await query.edit_message_reply_markup(None)

    if "mode" in context.user_data and context.user_data["mode"] == "update":
        records = [r for r in db.people_record(query.from_user.id, int(query.data))]
        await query.message.reply_text(
            trans.gettext("MESSAGE_DM_UPDATE_OCCUPATION {title} {occupation}").format(title=records[0]["title"],
                                                                                      occupation=records[0][
                                                                                          "occupation"]))
        user_data["category_title"] = records[0]["title"]
        user_data["location"] = records[0]["location"]
    else:
        await query.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_ASK_OCCUPATION"))

    return TYPING_OCCUPATION


async def received_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    user_data = context.user_data
    user_data["occupation"] = update.message.text

    trans = i18n.trans(update.message.from_user)

    if "mode" in context.user_data and context.user_data["mode"] == "update":
        await update.message.reply_text(
            trans.gettext("MESSAGE_DM_UPDATE_LOCATION {title} {location}").format(title=user_data["category_title"],
                                                                                  location=user_data["location"]))
    else:
        await update.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_ASK_LOCATION"))

    return TYPING_LOCATION


async def received_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the legality"""

    user_data = context.user_data
    user_data["location"] = update.message.text

    await update.message.reply_text(i18n.trans(update.message.from_user).gettext("MESSAGE_DM_ENROLL_CONFIRM_LEGALITY"),
                                    reply_markup=get_yesno_keyboard(update.message.from_user))

    return CONFIRMING_LEGALITY


async def confirm_legality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Complete the enrollment"""

    query = update.callback_query
    from_user = query.from_user

    await query.answer()

    user_data = context.user_data

    trans = i18n.trans(query.from_user)

    if query.data == RESPONSE_YES:
        db.people_insert_or_update(from_user.id, from_user.username, user_data["occupation"], user_data["location"],
                                   (0 if settings.SERVICES_MODERATION_IS_LAZY else 1), user_data["category_id"])

        saved_user_data = copy.deepcopy(user_data)
        user_data.clear()

        saved_user_data["tg_id"] = from_user.id
        saved_user_data["tg_username"] = from_user.username

        await query.edit_message_reply_markup(None)

        if not settings.SERVICES_MODERATION_ENABLED:
            message = trans.gettext("MESSAGE_DM_ENROLL_COMPLETED")
        elif settings.SERVICES_MODERATION_IS_LAZY:
            message = trans.gettext("MESSAGE_DM_ENROLL_COMPLETED_POST_MODERATION")
        else:
            message = trans.gettext("MESSAGE_DM_ENROLL_COMPLETED_PRE_MODERATION")

        await query.message.reply_text(message, reply_markup=get_standard_keyboard(from_user))

        if settings.SERVICES_MODERATION_ENABLED:
            await moderate_new_data(update, context, saved_user_data)

    elif query.data == RESPONSE_NO:
        db.people_delete(from_user.id, int(user_data["category_id"]))
        user_data.clear()

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(trans.gettext("MESSAGE_DM_ENROLL_DECLINED_ILLEGAL_SERVICE"),
                                       reply_markup=get_standard_keyboard(from_user))

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def confirm_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Approve or decline changes to user data"""

    query = update.callback_query

    await query.answer()

    command, tg_id, category_id = query.data.split(":")
    tg_id = int(tg_id)
    category_id = int(category_id)

    trans = i18n.trans(query.from_user)

    if command == MODERATOR_APPROVE:
        logging.info(
            "Moderator ID {moderator_id} approves new data from user ID {user_id} in category {category_id}".format(
                moderator_id=query.from_user.id, user_id=tg_id, category_id=category_id))

        if not settings.SERVICES_MODERATION_IS_LAZY:
            db.people_approve(tg_id, category_id)

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(trans.gettext("MESSAGE_ADMIN_USER_RECORD_APPROVED"))
    elif command == MODERATOR_DECLINE:
        logging.info(
            "Moderator ID {moderator_id} declines new data from user ID {user_id} in category {category_id}".format(
                moderator_id=query.from_user.id, user_id=tg_id, category_id=category_id))

        if settings.SERVICES_MODERATION_IS_LAZY:
            db.people_suspend(tg_id, category_id)

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(trans.gettext("MESSAGE_ADMIN_USER_RECORD_SUSPENDED"))
    else:
        logging.error("Unexpected query data: '{}'".format(query.data))

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def handle_command_retire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about removing an existing user record"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(i18n.trans(query.from_user).gettext("MESSAGE_DM_SELECT_CATEGORY_FOR_RETIRE"),
                                   reply_markup=get_category_keyboard(query.from_user,
                                                                      db.people_records(query.from_user.id)))

    return SELECTING_CATEGORY


async def retire_received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove the user record in a category selected on the previous step"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    db.people_delete(query.from_user.id, int(query.data))

    await show_main_status(context, query.message, query.from_user,
                           i18n.trans(query.from_user).gettext("MESSAGE_DM_RETIRE"))

    return ConversationHandler.END


async def abort_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reset the conversation state when it goes off track, and return to the starting point

    Used as fallback handler in stateful conversations with a regular user.
    """

    context.user_data.clear()

    user = update.effective_message.from_user

    await show_main_status(context, update.effective_message, user,
                           i18n.trans(user).gettext("MESSAGE_DM_CONVERSATION_CANCELLED"))

    return ConversationHandler.END


def init(application: Application, group: int):
    """Prepare the feature as defined in the configuration"""

    # Enrolling
    application.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(enroll, pattern=COMMAND_ENROLL),
                                                              CallbackQueryHandler(handle_command_update,
                                                                                   pattern=COMMAND_UPDATE)],
                                                states={SELECTING_CATEGORY: [CallbackQueryHandler(received_category)],
                                                        TYPING_OCCUPATION: [
                                                            MessageHandler(filters.TEXT & (~ filters.COMMAND),
                                                                           received_occupation)], TYPING_LOCATION: [
                                                        MessageHandler(filters.TEXT & (~ filters.COMMAND),
                                                                       received_location)],
                                                        CONFIRMING_LEGALITY: [CallbackQueryHandler(confirm_legality)]},
                                                fallbacks=[MessageHandler(filters.ALL, abort_conversation)]))

    application.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(who, pattern=COMMAND_WHO)], states={
        SELECTING_CATEGORY: [CallbackQueryHandler(who_received_category)]},
                                                fallbacks=[MessageHandler(filters.ALL, abort_conversation)]))

    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(handle_command_retire, pattern=COMMAND_RETIRE)],
                            states={SELECTING_CATEGORY: [CallbackQueryHandler(retire_received_category)]},
                            fallbacks=[MessageHandler(filters.ALL, abort_conversation)]))

    if settings.SERVICES_MODERATION_ENABLED:
        application.add_handler(CallbackQueryHandler(confirm_user_data, pattern=re.compile(
            "^({approve}|{decline}):[0-9]+:[0-9]+$".format(approve=MODERATOR_APPROVE, decline=MODERATOR_DECLINE))),
                                group=2)
