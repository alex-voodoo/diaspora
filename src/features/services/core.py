"""
Registry of services
"""

import copy
import gettext
import logging
import re
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

from common import i18n
from common.messaging_helpers import reply, send
from common.settings import settings
from . import admin, const, keyboards, state
from .state import Service, ServiceCategory


def _format_hint(text: str, limit: int) -> str:
    return f"<b>{text[:limit]}</b>{text[limit:limit + 10]}…"


def _format_deep_link_to_service(bot_username: str, category_id: int, tg_username: str) -> str:
    return f"t.me/{bot_username}?start=service_info_{category_id or 0}_{tg_username}"


def _maybe_append_limit_warning(trans: gettext.GNUTranslations, message: list, limit: int) -> None:
    """Perform one repeating part of conversation logic where a value is checked against length limit

    If `limit` is non-zero, appends a line that says that there is a limit.
    """

    if limit == 0:
        return

    message.append(trans.ngettext("SERVICES_DM_DATA_FIELD_LIMIT_S {limit}", "SERVICES_DM_DATA_FIELD_LIMIT_P {limit}",
                                  limit).format(limit=limit))


async def _verify_limit_then_retry_or_proceed(update: Update, context: ContextTypes.DEFAULT_TYPE, current_stage_id: int,
                                              current_limit: int, current_data_field_key: str, next_stage_id: int,
                                              next_limit: int, next_data_field_key: str,
                                              next_data_field_insert_text: str, next_data_field_update_text: str,
                                              request_next_data_field: Callable[
                                                  [Update, ContextTypes.DEFAULT_TYPE, int, str, str, str], Awaitable[
                                                      None]]) -> int:
    """Perform one repeating part of conversation logic where a value is checked against length limit

    If the value that comes in the `update.message` is longer than `current_limit`, the function displays a warning and
    returns `current_stage_id`, effectively asking the user for a corrected value and not advancing them to the next
    step. Otherwise, `request_next_data_field` is called, and then `next_stage_id` is returned, thus stepping the
    conversation forward.
    """

    message = update.message

    trans = i18n.trans(message.from_user)

    new_text = message.text.strip()
    if 0 < current_limit < len(new_text):
        new_text = _format_hint(new_text, current_limit)
        await reply(update, trans.ngettext("SERVICES_DM_TEXT_TOO_LONG_S {limit} {text}",
                                           "SERVICES_DM_TEXT_TOO_LONG_P {limit} {text}", current_limit).format(
            limit=current_limit, text=new_text))
        return current_stage_id

    user_data = context.user_data
    user_data[current_data_field_key] = new_text

    await request_next_data_field(update, context, next_limit, next_data_field_key, next_data_field_insert_text,
                                  next_data_field_update_text)

    return next_stage_id


async def _request_next_data_field(update: Update, context: ContextTypes.DEFAULT_TYPE, next_limit: int,
                                   next_data_field_key: str, next_data_field_insert_text: str,
                                   next_data_field_update_text: str) -> None:
    """Perform one repeating part of conversation logic where a value is checked against length limit

    Sends a message that asks the user to enter the next data field.
    """

    message = update.message

    trans = i18n.trans(message.from_user)
    user_data = context.user_data

    lines = []
    if "mode" in user_data and user_data["mode"] == "update":
        lines.append(next_data_field_update_text.format(title=user_data["category_title"],
                                                        current_value=user_data[next_data_field_key]))
    else:
        lines.append(next_data_field_insert_text)

    _maybe_append_limit_warning(trans, lines, next_limit)
    await reply(update, "\n".join(lines))


def _main_status_record_description(service: Service) -> str:
    return (f"<b>{service.category.title}:</b> <a href=\"{service.deep_link}\">{service.occupation}</a> ("
            f"{service.location})")


async def show_main_status(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix="") -> None:
    """Show the current status of the user"""

    user = update.effective_user

    records = [r for r in state.Service.get_all_by_user(user.id)]

    trans = i18n.trans(user)

    if records:
        logging.info("This is {username} that has records already".format(username=user.username))

        text = []
        if prefix:
            text.append(prefix)
        if len(records) == 1:
            text.append(
                trans.gettext("SERVICES_DM_HELLO_AGAIN {user_first_name}").format(user_first_name=user.first_name))
        else:
            text.append(trans.ngettext("SERVICES_DM_HELLO_AGAIN_S {user_first_name} {record_count}",
                                       "SERVICES_DM_HELLO_AGAIN_P {user_first_name} {record_count}",
                                       len(records)).format(user_first_name=user.first_name, record_count=len(records)))

        for record in records:
            text.append(_main_status_record_description(record))

        await reply(update, "\n".join(text), keyboards.standard(user))
    else:
        logging.info("Welcoming user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

        if prefix:
            text = prefix + "\n" + trans.gettext("SERVICES_DM_NO_RECORDS")
        else:
            main_chat = await context.bot.get_chat(settings.MAIN_CHAT_ID)

            text = trans.gettext("SERVICES_DM_HELLO {bot_first_name} {main_chat_name}").format(
                bot_first_name=context.bot.first_name, main_chat_name=main_chat.title)

        await reply(update, text, keyboards.standard(user))


async def _moderate_new_data(context: ContextTypes.DEFAULT_TYPE, data) -> None:
    moderator_ids = [a["id"] for a in settings.ADMINISTRATORS] if settings.ADMINISTRATORS else (
        settings.DEVELOPER_CHAT_ID,)

    for moderator_id in moderator_ids:
        logging.info("Sending moderation request to moderator ID {id}".format(id=moderator_id))
        await send(context, moderator_id, i18n.default().gettext(
            "SERVICES_ADMIN_APPROVE_USER_DATA {category} {description} {location} {occupation} {username}").format(
            category=data["category_title"], description=data["description"], location=data["location"],
            occupation=data["occupation"], username=data["tg_username"]), keyboards.approve_service_change(data))


def _who_people_to_message(people: list[Service]) -> list[str]:
    result = []
    for p in people:
        result.append(f"- @{p.tg_username} ({p.location}): <a href=\"{p.deep_link}\">{p.occupation}</a>")
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

    trans = i18n.trans(query.from_user)
    await reply(update, trans.gettext("SERVICES_DM_WHO_CATEGORY_LIST").format(
        categories="\n".join([c["text"] for c in category_list])), keyboards.select_category(trans, category_list))

    context.user_data["who_request_category"] = filtered_people

    return const.SELECTING_CATEGORY


async def _who_received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List users in the category that the user selected previously"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    filtered_people = context.user_data["who_request_category"]
    category_id = int(query.data)

    state.people_category_views_register(query.from_user.id, category_id)

    category = None
    for c in filtered_people:
        if c["category_id"] == category_id:
            category = c
            break
    if not category:
        await reply(update, i18n.trans(query.from_user).gettext("SERVICES_DM_WHO_CATEGORY_EMPTY"),
                    keyboards.standard(query.from_user))
        return ConversationHandler.END

    user_list = ["<b>{t}</b>".format(t=category["title"])] + _who_people_to_message(category["people"])

    await reply(update, "\n".join(user_list), keyboards.standard(query.from_user))

    del context.user_data["who_request_category"]
    return ConversationHandler.END


async def _who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the current registry"""

    query = update.callback_query

    await query.answer()

    trans = i18n.trans(query.from_user)

    user_list = [trans.gettext("SERVICES_DM_WHO_LIST_HEADING")]

    categorised_people = {0: {"title": trans.gettext("SERVICES_CATEGORY_OTHER_TITLE"), "category_id": 0, "people": []}}

    for category in ServiceCategory.all():
        categorised_people[category.id] = {"title": category.title, "people": []}

    for service in state.Service.get_all_active():
        categorised_people[service.category.id]["people"].append(service)

    filtered_people = [{"title": c["title"], "category_id": i, "people": c["people"]} for i, c in
                       categorised_people.items() if i != 0 and c["people"]]
    if categorised_people[0]["people"]:
        filtered_people.append(categorised_people[0])

    state.people_category_views_register(query.from_user.id, -1)

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
            await reply(update, united_message, keyboards.standard(query.from_user))
            return ConversationHandler.END
        else:
            return await _who_request_category(update, context, filtered_people)


async def _handle_command_enroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about adding a new user record"""

    query = update.callback_query

    trans = i18n.trans(query.from_user)

    await query.answer()
    await query.edit_message_reply_markup(None)

    if not query.from_user.username:
        await reply(update, trans.gettext("SERVICES_DM_ENROLL_USERNAME_REQUIRED"), keyboards.standard(query.from_user))
        return ConversationHandler.END

    await reply(update, trans.gettext("SERVICES_DM_ENROLL_START"))

    existing_category_ids = [service.category.id for service in state.Service.get_all_by_user(query.from_user.id)]
    categories = [{"id": c.id, "title": c.title} for c in ServiceCategory.all() if c.id not in existing_category_ids]

    category_buttons = keyboards.select_category(trans, categories, 0 not in existing_category_ids)

    if category_buttons:
        await reply(update, trans.gettext("SERVICES_DM_ENROLL_ASK_CATEGORY"), category_buttons)

        return const.SELECTING_CATEGORY
    else:
        user_data = context.user_data
        user_data["category_id"] = 0

        await reply(update, trans.gettext("SERVICES_DM_ENROLL_ASK_OCCUPATION"))

        return const.TYPING_OCCUPATION


async def _handle_command_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about updating an existing user record"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    trans = i18n.trans(query.from_user)
    await reply(update, trans.gettext("SERVICES_DM_SELECT_CATEGORY_FOR_UPDATE"),
                keyboards.select_category(trans, state.Service.get_all_by_user(query.from_user.id)))

    context.user_data["mode"] = "update"

    return const.SELECTING_CATEGORY


async def _accept_category_and_request_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input"""

    query = update.callback_query
    user = query.from_user

    trans = i18n.trans(user)

    user_data = context.user_data
    category_id = int(query.data)

    user_data["category_id"] = category_id

    await query.answer()
    await query.edit_message_reply_markup(None)

    lines = []
    if "mode" in context.user_data and context.user_data["mode"] == "update":
        service = state.Service.get(user.id, category_id)
        user_data["category_title"] = service.category.title
        user_data["location"] = service.location
        user_data["occupation"] = service.occupation
        user_data["description"] = service.description

        lines.append(trans.gettext("SERVICES_DM_UPDATE_OCCUPATION {title} {current_value}").format(
            title=user_data["category_title"], current_value=user_data["occupation"]))
    else:
        user_data["category_title"] = state.ServiceCategory.get(category_id).title

        lines.append(trans.gettext("SERVICES_DM_ENROLL_ASK_OCCUPATION"))

    _maybe_append_limit_warning(trans, lines, settings.SERVICES_OCCUPATION_MAX_LENGTH)
    await reply(update, "\n".join(lines))
    return const.TYPING_OCCUPATION


async def _verify_occupation_and_request_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store occupation provided by user and ask for the next category"""

    if not update.message:
        logging.warning("Ignoring an update that does not have a message.")
        return const.TYPING_OCCUPATION

    trans = i18n.trans(update.message.from_user)

    return await _verify_limit_then_retry_or_proceed(update, context, const.TYPING_OCCUPATION,
                                                     settings.SERVICES_OCCUPATION_MAX_LENGTH, "occupation",
                                                     const.TYPING_DESCRIPTION, settings.SERVICES_DESCRIPTION_MAX_LENGTH,
                                                     "description", trans.gettext("SERVICES_DM_ENROLL_ASK_DESCRIPTION"),
                                                     trans.gettext(
                                                         "SERVICES_DM_UPDATE_DESCRIPTION {title} {current_value}"),
                                                     _request_next_data_field)


async def _verify_description_and_request_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category"""

    if not update.message:
        logging.warning("Ignoring an update that does not have a message.")
        return const.TYPING_DESCRIPTION

    trans = i18n.trans(update.message.from_user)

    return await _verify_limit_then_retry_or_proceed(update, context, const.TYPING_DESCRIPTION,
                                                     settings.SERVICES_DESCRIPTION_MAX_LENGTH, "description",
                                                     const.TYPING_LOCATION, settings.SERVICES_LOCATION_MAX_LENGTH,
                                                     "location", trans.gettext("SERVICES_DM_ENROLL_ASK_LOCATION"),
                                                     trans.gettext(
                                                         "SERVICES_DM_UPDATE_LOCATION {title} {current_value}"),
                                                     _request_next_data_field)


async def _verify_location_and_request_legality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store location info provided by user and ask for the legality"""

    if not update.message:
        logging.warning("Ignoring an update that does not have a message.")
        return const.TYPING_LOCATION

    trans = i18n.trans(update.message.from_user)

    async def request_legality(*_args) -> None:
        await reply(update, trans.gettext("SERVICES_DM_ENROLL_CONFIRM_LEGALITY"), keyboards.yes_no(trans))

    return await _verify_limit_then_retry_or_proceed(update, context, const.TYPING_LOCATION,
                                                     settings.SERVICES_LOCATION_MAX_LENGTH, "location",
                                                     const.CONFIRMING_LEGALITY, 0, "", "", "", request_legality)


async def _verify_legality_and_finalise_data_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Complete the conversation where information about user's service was gathered

    Checks if the user confirmed that their service does not violate the law, and if yes, saves the new data, optionally
    asking the moderators to verify it, then ends the conversation.
    """

    query = update.callback_query
    from_user = query.from_user

    await query.answer()

    user_data = context.user_data

    trans = i18n.trans(query.from_user)

    if query.data == const.RESPONSE_YES:
        state.Service.set(from_user.id, from_user.username, user_data["occupation"], user_data["description"],
                          user_data["location"], not settings.SERVICES_MODERATION_IS_LAZY, user_data["category_id"])

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

        await reply(update, message, keyboards.standard(from_user))

        if settings.SERVICES_MODERATION_ENABLED:
            await _moderate_new_data(context, saved_user_data)

    elif query.data == const.RESPONSE_NO:
        state.Service.delete(from_user.id, int(user_data["category_id"]))
        user_data.clear()

        await query.edit_message_reply_markup(None)
        await reply(update, trans.gettext("SERVICES_DM_ENROLL_DECLINED_ILLEGAL_SERVICE"), keyboards.standard(from_user))

    return ConversationHandler.END


async def _confirm_user_data(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
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
            state.Service.set_is_suspended(tg_id, category_id, False)

        await query.edit_message_reply_markup(None)
        await reply(update, trans.gettext("SERVICES_ADMIN_USER_RECORD_APPROVED"))
    elif command == const.MODERATOR_DECLINE:
        logging.info(
            "Moderator ID {moderator_id} declines new data from user ID {user_id} in category {category_id}".format(
                moderator_id=query.from_user.id, user_id=tg_id, category_id=category_id))

        if settings.SERVICES_MODERATION_IS_LAZY:
            state.Service.set_is_suspended(tg_id, category_id, True)

        await query.edit_message_reply_markup(None)
        await reply(update, trans.gettext("SERVICES_ADMIN_USER_RECORD_SUSPENDED"))
    else:
        logging.error("Unexpected query data: '{}'".format(query.data))

    return ConversationHandler.END


async def _handle_command_retire(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation about removing an existing user record"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    trans = i18n.trans(query.from_user)
    await reply(update, trans.gettext("SERVICES_DM_SELECT_CATEGORY_FOR_RETIRE"),
                keyboards.select_category(trans, state.Service.get_all_by_user(query.from_user.id)))

    return const.SELECTING_CATEGORY


async def _retire_received_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove the user record in a category selected on the previous step"""

    query = update.callback_query

    await query.answer()
    await query.edit_message_reply_markup(None)

    state.Service.delete(query.from_user.id, int(query.data))

    await show_main_status(update, context, i18n.trans(query.from_user).gettext("SERVICES_DM_RETIRE"))

    return ConversationHandler.END


async def _abort_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reset the conversation state when it goes off track, and return to the starting point

    Used as fallback handler in stateful conversations with a regular user.
    """

    context.user_data.clear()

    await show_main_status(update, context,
                           i18n.trans(update.effective_user).gettext("SERVICES_DM_CONVERSATION_CANCELLED"))

    return ConversationHandler.END


async def handle_extended_start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    param = update.effective_message.text.split(" ")[1]
    if not param.startswith(const.COMMAND_INFO + "_"):
        return

    category_id, tg_username = param[len(const.COMMAND_INFO + "_"):].split("_", 1)
    category_id = int(category_id)

    user = update.effective_message.from_user

    trans = i18n.trans(user)

    service = state.Service.get_by_username(tg_username, category_id)

    state.people_views_register(user.id, service.tg_id, category_id)

    if user.id == service.tg_id:
        await reply(update, trans.gettext(
            "SERVICES_DM_YOUR_SERVICE_INFO {category_title} {description} {location} {occupation}").format(
            category_title=service.category.title, description=service.description, location=service.location,
            occupation=service.occupation))
    else:
        await reply(update, trans.gettext(
            "SERVICES_DM_SERVICE_INFO {category_title} {description} {location} {occupation} {username}").format(
            category_title=service.category.title, description=service.description, location=service.location,
            occupation=service.occupation, username=service.tg_username))


def post_init(application: Application) -> None:
    # noinspection PyUnresolvedReferences
    Service.set_bot_username(application.bot.username)


def init(application: Application, group: int) -> None:
    """Prepare the feature as defined in the configuration"""

    # Enrolling
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(_handle_command_enroll, pattern=const.COMMAND_ENROLL),
                      CallbackQueryHandler(_handle_command_update, pattern=const.COMMAND_UPDATE)],
        states={const.SELECTING_CATEGORY: [CallbackQueryHandler(_accept_category_and_request_occupation)],
                const.TYPING_OCCUPATION: [
                    MessageHandler(filters.TEXT & (~ filters.COMMAND), _verify_occupation_and_request_description)],
                const.TYPING_DESCRIPTION: [
                    MessageHandler(filters.TEXT & (~ filters.COMMAND), _verify_description_and_request_location)],
                const.TYPING_LOCATION: [
                    MessageHandler(filters.TEXT & (~ filters.COMMAND), _verify_location_and_request_legality)],
                const.CONFIRMING_LEGALITY: [CallbackQueryHandler(_verify_legality_and_finalise_data_collection)]},
        fallbacks=[MessageHandler(filters.ALL, _abort_conversation)]), group=group)

    application.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(_who, pattern=const.COMMAND_WHO)],
                                                states={const.SELECTING_CATEGORY: [
                                                    CallbackQueryHandler(_who_received_category)]},
                                                fallbacks=[MessageHandler(filters.ALL, _abort_conversation)]),
                            group=group)

    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(_handle_command_retire, pattern=const.COMMAND_RETIRE)],
                            states={const.SELECTING_CATEGORY: [CallbackQueryHandler(_retire_received_category)]},
                            fallbacks=[MessageHandler(filters.ALL, _abort_conversation)]), group=group)

    admin.register_handlers(application, group)

    if settings.SERVICES_MODERATION_ENABLED:
        application.add_handler(CallbackQueryHandler(_confirm_user_data, pattern=re.compile(
            "^({approve}|{decline}):[0-9]+:[0-9]+$".format(approve=const.MODERATOR_APPROVE,
                                                           decline=const.MODERATOR_DECLINE))), group=2)

    ServiceCategory.load()
