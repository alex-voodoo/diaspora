"""
Registry of services
"""

import copy
import logging
import re

from telegram import Message, Update, User
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

from common import i18n
from common.settings import settings
from . import const, keyboards, state


def _maybe_append_limit_warning(trans, message: list, limit: int) -> None:
    if limit == 0:
        return

    message.append(trans.ngettext("SERVICES_DM_DATA_FIELD_LIMIT_S {limit}", "SERVICES_DM_DATA_FIELD_LIMIT_P {limit}",
                                  limit).format(limit=limit))


def _maybe_apply_limit(text: str, limit: int) -> str:
    text = text.strip()
    return text[:limit] if limit else text


async def show_main_status(context: ContextTypes.DEFAULT_TYPE, message: Message, user: User, prefix="") -> None:
    """Show the current status of the user"""

    records = [r for r in state.people_records(user.id)]

    trans = i18n.trans(user)

    if records:
        logging.info("This is {username} that has records already".format(username=user.username))

        def get_header():
            if len(records) == 1:
                return trans.gettext("SERVICES_DM_HELLO_AGAIN {user_first_name}").format(
                    user_first_name=user.first_name)
            return trans.ngettext("SERVICES_DM_HELLO_AGAIN_S {user_first_name} {record_count}",
                                  "SERVICES_DM_HELLO_AGAIN_P {user_first_name} {record_count}", len(records)).format(
                user_first_name=user.first_name, record_count=len(records))

        text = []
        if prefix:
            text.append(prefix)
        text.append(get_header())

        for record in records:
            text.append("<b>{c}:</b> {o} ({l})".format(
                c=record["title"] if record["title"] else trans.gettext("SERVICES_BUTTON_ENROLL_CATEGORY_DEFAULT"),
                o=record["occupation"], l=record["location"]))

        await message.reply_text("\n".join(text), reply_markup=keyboards.standard(user))
    else:
        logging.info("Welcoming user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

        if prefix:
            text = prefix + "\n" + trans.gettext("SERVICES_DM_NO_RECORDS")
        else:
            main_chat = await context.bot.get_chat(settings.MAIN_CHAT_ID)

            text = trans.gettext("SERVICES_DM_HELLO {bot_first_name} {main_chat_name}").format(
                bot_first_name=context.bot.first_name, main_chat_name=main_chat.title)

        await message.reply_text(text, reply_markup=keyboards.standard(user))


# noinspection PyUnusedLocal
async def _moderate_new_data(update: Update, context: ContextTypes.DEFAULT_TYPE, data) -> None:
    moderator_ids = [admin["id"] for admin in settings.ADMINISTRATORS] if settings.ADMINISTRATORS else (
        settings.DEVELOPER_CHAT_ID,)

    for moderator_id in moderator_ids:
        logging.info("Sending moderation request to moderator ID {id}".format(id=moderator_id))
        await context.bot.send_message(chat_id=moderator_id, text=i18n.default().gettext(
            "SERVICES_ADMIN_APPROVE_USER_DATA {username}").format(username=data["tg_username"],
                                                                  occupation=data["occupation"],
                                                                  location=data["location"]),
                                       reply_markup=keyboards.approve_service_change(data))


def _who_people_to_message(people: list) -> list:
    result = []
    for p in people:
        link = f"t.me/PeopleRegistryBot?start=service_info_{p["category_id"]}_{p["tg_username"]}"
        result.append(f"- @{p["tg_username"]} ({p["location"]}): <a href=\"{link}\">{p["occupation"]}</a>")
    return result


async def _who_request_category(update: Update, context: ContextTypes.DEFAULT_TYPE, filtered_people: list) -> int:
    """Ask user for a category to show"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    category_list = []

    for c in filtered_people:
        category_list.append(
            {"id": c["category_id"], "title": c["title"], "text": "{t}: {c}".format(t=c["title"], c=len(c["people"]))})

    await query.message.reply_text(i18n.trans(query.from_user).gettext("SERVICES_DM_WHO_CATEGORY_LIST").format(
        categories="\n".join([c["text"] for c in category_list])),
        reply_markup=keyboards.select_category(query.from_user, category_list))

    context.user_data["who_request_category"] = filtered_people

    return const.SELECTING_CATEGORY


async def _who_received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        await query.message.reply_text(text=i18n.trans(query.from_user).gettext("SERVICES_DM_WHO_CATEGORY_EMPTY"),
                                       reply_markup=keyboards.standard(query.from_user))
        return ConversationHandler.END

    user_list = ["<b>{t}</b>".format(t=category["title"])] + _who_people_to_message(category["people"])

    await query.message.reply_text(text="\n".join(user_list), reply_markup=keyboards.standard(query.from_user))

    del context.user_data["who_request_category"]
    return ConversationHandler.END


# noinspection PyUnusedLocal
async def _who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the current registry"""

    query = update.callback_query

    await query.answer()

    trans = i18n.trans(query.from_user)

    user_list = [trans.gettext("SERVICES_DM_WHO_LIST_HEADING")]

    categorised_people = {
        0: {"title": trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"), "category_id": 0, "people": []}}

    for category in state.people_category_select_all():
        categorised_people[category["id"]] = {"title": category["title"], "people": []}

    for person in state.people_select_all():
        if "category_id" not in person or person["category_id"] not in categorised_people:
            person["category_id"] = 0
        categorised_people[person["category_id"]]["people"].append(person)

    filtered_people = [{"title": c["title"], "category_id": i, "people": c["people"]} for i, c in
                       categorised_people.items() if i != 0 and c["people"]]
    if categorised_people[0]["people"]:
        filtered_people.append(categorised_people[0])

    if settings.SHOW_CATEGORIES_ALWAYS and len(filtered_people) > 1:
        return await _who_request_category(update, context, filtered_people)
    else:
        if len(filtered_people) == 1:
            user_list += _who_people_to_message(filtered_people[0]["people"])
        else:
            for category in filtered_people:
                user_list.append("")
                user_list.append("<b>{t}</b>".format(t=category["title"]))
                user_list += _who_people_to_message(category["people"])

        if len(user_list) == 1:
            user_list = [trans.gettext("SERVICES_DM_WHO_EMPTY")]

        united_message = "\n".join(user_list)
        if len(united_message) < settings.MAX_MESSAGE_LENGTH:
            await query.edit_message_reply_markup(None)
            await query.message.reply_text(text=united_message, reply_markup=keyboards.standard(query.from_user))
            return ConversationHandler.END
        else:
            return await _who_request_category(update, context, filtered_people)


# noinspection PyUnusedLocal
async def _enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about adding the first user record"""

    query = update.callback_query

    trans = i18n.trans(query.from_user)

    await query.answer()
    await query.edit_message_reply_markup(None)

    if not query.from_user.username:
        await query.message.reply_text(trans.gettext("SERVICES_DM_ENROLL_USERNAME_REQUIRED"),
                                       reply_markup=keyboards.standard(query.from_user))
        return ConversationHandler.END

    await query.message.reply_text(trans.gettext("SERVICES_DM_ENROLL_START"))

    existing_category_ids = [r["id"] for r in state.people_records(query.from_user.id)]
    categories = [c for c in state.people_category_select_all() if c["id"] not in existing_category_ids]

    category_buttons = keyboards.select_category(query.from_user, categories, 0 not in existing_category_ids)

    if category_buttons:
        await query.message.reply_text(trans.gettext("SERVICES_DM_ENROLL_ASK_CATEGORY"), reply_markup=category_buttons)

        return const.SELECTING_CATEGORY
    else:
        user_data = context.user_data
        user_data["category_id"] = 0

        await query.message.reply_text(trans.gettext("SERVICES_DM_ENROLL_ASK_OCCUPATION"))

        return const.TYPING_OCCUPATION


# noinspection PyUnusedLocal
async def _handle_command_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about updating an existing user record"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(i18n.trans(query.from_user).gettext("SERVICES_DM_SELECT_CATEGORY_FOR_UPDATE"),
                                   reply_markup=keyboards.select_category(query.from_user,
                                                                          state.people_records(query.from_user.id)))

    context.user_data["mode"] = "update"

    return const.SELECTING_CATEGORY


async def _received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    query = update.callback_query

    trans = i18n.trans(query.from_user)

    user_data = context.user_data
    user_data["category_id"] = int(query.data)

    await query.answer()
    await query.edit_message_reply_markup(None)

    lines = []
    if "mode" in context.user_data and context.user_data["mode"] == "update":
        records = [r for r in state.people_record(int(query.data), tg_id=query.from_user.id)]
        user_data["category_title"] = records[0]["title"] if user_data["category_id"] != 0 else trans.gettext(
            "SERVICES_CATEGORY_OTHER_TITLE")
        user_data["location"] = records[0]["location"]
        user_data["occupation"] = records[0]["occupation"]
        user_data["description"] = records[0]["description"]

        lines.append(
            trans.gettext("SERVICES_DM_UPDATE_OCCUPATION {title} {occupation}").format(
                title=user_data["category_title"], occupation=user_data["occupation"]))
    else:
        lines.append(trans.gettext("SERVICES_DM_ENROLL_ASK_OCCUPATION"))

    _maybe_append_limit_warning(trans, lines, settings.SERVICES_OCCUPATION_MAX_LENGTH)
    await query.message.reply_text("\n".join(lines))
    return const.TYPING_OCCUPATION


async def _received_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    user_data = context.user_data
    user_data["occupation"] = _maybe_apply_limit(update.message.text, settings.SERVICES_OCCUPATION_MAX_LENGTH)

    trans = i18n.trans(update.message.from_user)

    lines = []
    if "mode" in context.user_data and context.user_data["mode"] == "update":
        lines.append(
            trans.gettext("SERVICES_DM_UPDATE_DESCRIPTION {title} {description}").format(
                title=user_data["category_title"],
                description=user_data["description"]))
    else:
        lines.append(trans.gettext("SERVICES_DM_ENROLL_ASK_DESCRIPTION"))

    _maybe_append_limit_warning(trans, lines, settings.SERVICES_DESCRIPTION_MAX_LENGTH)
    await update.message.reply_text("\n".join(lines))
    return const.TYPING_DESCRIPTION


async def _received_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    user_data = context.user_data
    user_data["description"] = _maybe_apply_limit(update.message.text, settings.SERVICES_DESCRIPTION_MAX_LENGTH)

    trans = i18n.trans(update.message.from_user)

    lines = []
    if "mode" in context.user_data and context.user_data["mode"] == "update":
        lines.append(
            trans.gettext("SERVICES_DM_UPDATE_LOCATION {title} {location}").format(title=user_data["category_title"],
                                                                                   location=user_data["location"]))
    else:
        lines.append(trans.gettext("SERVICES_DM_ENROLL_ASK_LOCATION"))

    _maybe_append_limit_warning(trans, lines, settings.SERVICES_LOCATION_MAX_LENGTH)
    await update.message.reply_text("\n".join(lines))
    return const.TYPING_LOCATION


async def _received_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the legality"""

    user_data = context.user_data
    user_data["location"] = _maybe_apply_limit(update.message.text, settings.SERVICES_LOCATION_MAX_LENGTH)

    await update.message.reply_text(i18n.trans(update.message.from_user).gettext("SERVICES_DM_ENROLL_CONFIRM_LEGALITY"),
                                    reply_markup=keyboards.yes_no(update.message.from_user))

    return const.CONFIRMING_LEGALITY


async def _confirm_legality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Complete the enrollment"""

    query = update.callback_query
    from_user = query.from_user

    await query.answer()

    user_data = context.user_data

    trans = i18n.trans(query.from_user)

    if query.data == const.RESPONSE_YES:
        state.people_insert_or_update(from_user.id, from_user.username, user_data["occupation"],
                                      user_data["description"], user_data["location"],
                                      (0 if settings.SERVICES_MODERATION_IS_LAZY else 1), user_data["category_id"])

        saved_user_data = copy.deepcopy(user_data)
        user_data.clear()

        saved_user_data["tg_id"] = from_user.id
        saved_user_data["tg_username"] = from_user.username

        await query.edit_message_reply_markup(None)

        if not settings.SERVICES_MODERATION_ENABLED:
            message = trans.gettext("SERVICES_DM_ENROLL_COMPLETED")
        elif settings.SERVICES_MODERATION_IS_LAZY:
            message = trans.gettext("SERVICES_DM_ENROLL_COMPLETED_POST_MODERATION")
        else:
            message = trans.gettext("SERVICES_DM_ENROLL_COMPLETED_PRE_MODERATION")

        await query.message.reply_text(message, reply_markup=keyboards.standard(from_user))

        if settings.SERVICES_MODERATION_ENABLED:
            await _moderate_new_data(update, context, saved_user_data)

    elif query.data == const.RESPONSE_NO:
        state.people_delete(from_user.id, int(user_data["category_id"]))
        user_data.clear()

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(trans.gettext("SERVICES_DM_ENROLL_DECLINED_ILLEGAL_SERVICE"),
                                       reply_markup=keyboards.standard(from_user))

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def _confirm_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Approve or decline changes to user data"""

    query = update.callback_query

    await query.answer()

    command, tg_id, category_id = query.data.split(":")
    tg_id = int(tg_id)
    category_id = int(category_id)

    trans = i18n.trans(query.from_user)

    if command == const.MODERATOR_APPROVE:
        logging.info(
            "Moderator ID {moderator_id} approves new data from user ID {user_id} in category {category_id}".format(
                moderator_id=query.from_user.id, user_id=tg_id, category_id=category_id))

        if not settings.SERVICES_MODERATION_IS_LAZY:
            state.people_approve(tg_id, category_id)

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(trans.gettext("SERVICES_ADMIN_USER_RECORD_APPROVED"))
    elif command == const.MODERATOR_DECLINE:
        logging.info(
            "Moderator ID {moderator_id} declines new data from user ID {user_id} in category {category_id}".format(
                moderator_id=query.from_user.id, user_id=tg_id, category_id=category_id))

        if settings.SERVICES_MODERATION_IS_LAZY:
            state.people_suspend(tg_id, category_id)

        await query.edit_message_reply_markup(None)
        await query.message.reply_text(trans.gettext("SERVICES_ADMIN_USER_RECORD_SUSPENDED"))
    else:
        logging.error("Unexpected query data: '{}'".format(query.data))

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def _handle_command_retire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about removing an existing user record"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(i18n.trans(query.from_user).gettext("SERVICES_DM_SELECT_CATEGORY_FOR_RETIRE"),
                                   reply_markup=keyboards.select_category(query.from_user,
                                                                          state.people_records(query.from_user.id)))

    return const.SELECTING_CATEGORY


async def _retire_received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove the user record in a category selected on the previous step"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    state.people_delete(query.from_user.id, int(query.data))

    await show_main_status(context, query.message, query.from_user,
                           i18n.trans(query.from_user).gettext("SERVICES_DM_RETIRE"))

    return ConversationHandler.END


async def _abort_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reset the conversation state when it goes off track, and return to the starting point

    Used as fallback handler in stateful conversations with a regular user.
    """

    context.user_data.clear()

    user = update.effective_message.from_user

    await show_main_status(context, update.effective_message, user,
                           i18n.trans(user).gettext("SERVICES_DM_CONVERSATION_CANCELLED"))

    return ConversationHandler.END


async def handle_extended_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    param = update.effective_message.text.split(" ")[1]
    if not param.startswith(const.COMMAND_INFO + "_"):
        return

    category_id, tg_username = param[len(const.COMMAND_INFO + "_"):].split("_")
    category_id = int(category_id)
    trans = i18n.trans(update.effective_message.from_user)
    for record in state.people_record(category_id, tg_username=tg_username):
        category_title = record["title"] if category_id != 0 else trans.gettext("SERVICES_CATEGORY_OTHER_TITLE")
        await update.effective_message.reply_text(trans.gettext(
            "SERVICES_DM_SERVICE_INFO {category_title} {description} {location} {occupation} {username}").format(
            category_title=category_title, description=record["description"], location=record["location"],
            occupation=record["occupation"], username=tg_username))


def init(application: Application, group: int):
    """Prepare the feature as defined in the configuration"""

    # Enrolling
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(_enroll, pattern=const.COMMAND_ENROLL),
                      CallbackQueryHandler(_handle_command_update, pattern=const.COMMAND_UPDATE)],
        states={const.SELECTING_CATEGORY: [CallbackQueryHandler(_received_category)],
                const.TYPING_OCCUPATION: [MessageHandler(filters.TEXT & (~ filters.COMMAND), _received_occupation)],
                const.TYPING_DESCRIPTION: [MessageHandler(filters.TEXT & (~ filters.COMMAND), _received_description)],
                const.TYPING_LOCATION: [MessageHandler(filters.TEXT & (~ filters.COMMAND), _received_location)],
                const.CONFIRMING_LEGALITY: [CallbackQueryHandler(_confirm_legality)]},
        fallbacks=[MessageHandler(filters.ALL, _abort_conversation)]))

    application.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(_who, pattern=const.COMMAND_WHO)],
                                                states={const.SELECTING_CATEGORY: [
                                                    CallbackQueryHandler(_who_received_category)]},
                                                fallbacks=[MessageHandler(filters.ALL, _abort_conversation)]))

    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(_handle_command_retire, pattern=const.COMMAND_RETIRE)],
                            states={const.SELECTING_CATEGORY: [CallbackQueryHandler(_retire_received_category)]},
                            fallbacks=[MessageHandler(filters.ALL, _abort_conversation)]))

    if settings.SERVICES_MODERATION_ENABLED:
        application.add_handler(CallbackQueryHandler(_confirm_user_data, pattern=re.compile(
            "^({approve}|{decline}):[0-9]+:[0-9]+$".format(approve=const.MODERATOR_APPROVE,
                                                           decline=const.MODERATOR_DECLINE))), group=2)
