"""
Admin functions of the Services feature
"""
import datetime
import io
import json
import logging
import pathlib

import jsonschema
from telegram import InlineKeyboardButton, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

from common import i18n
from common.admin import get_main_keyboard, register_buttons, has_attachment
from common.checks import is_admin
from common.messaging_helpers import reply
from common.settings import settings
from . import state

_ADMIN_EXPORT_DB, _ADMIN_IMPORT_DB, _ADMIN_STATS = (
    "services-admin-export-db", "services-admin-import-db", "services-admin-stats")
_ADMIN_UPLOADING_DB = 1
_STATS_PERIOD_DAYS = 30


async def _handle_query(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None | int:
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == _ADMIN_EXPORT_DB:
        await user.send_document(json.dumps(state.export_db(), ensure_ascii=False, indent=2).encode("utf-8"),
                                 filename="services.json", reply_markup=None)
    elif query.data == _ADMIN_IMPORT_DB:
        await reply(update, trans.gettext("SERVICES_MESSAGE_DM_ADMIN_REQUEST_DB"))

        return _ADMIN_UPLOADING_DB
    elif query.data == _ADMIN_STATS:
        await _show_stats(update)


async def _handle_received_db(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    trans = i18n.trans(update.effective_user)

    success, error_message = has_attachment(update, "application/json")
    if not success:
        await reply(update, error_message, get_main_keyboard())
        return ConversationHandler.END

    db_file = await update.effective_message.document.get_file()
    data = io.BytesIO()
    await db_file.download_to_memory(data)
    data.seek(0)

    try:
        data = json.load(data)
        schema = json.load(open(pathlib.Path(__file__).parent / "schema.json"))

        jsonschema.validate(data, schema)
        # TODO: Validate data integrity.

        state.import_db(data)

        await reply(update, trans.gettext("SERVICES_MESSAGE_DM_ADMIN_DB_IMPORTED"))
    except jsonschema.ValidationError as e:
        logging.error(e)
        await reply(update, trans.gettext("SERVICES_MESSAGE_DM_ADMIN_INVALID_JSON"), get_main_keyboard())
    except Exception as e:
        logging.error(e)
        await reply(update, trans.gettext("ADMIN_MESSAGE_DM_INTERNAL_ERROR"), get_main_keyboard())

    return ConversationHandler.END


async def _show_stats(update: Update) -> None:
    trans = i18n.trans(update.effective_user)

    from_date = datetime.datetime.now() - datetime.timedelta(days=_STATS_PERIOD_DAYS)

    def get_view_count_text(count: int) -> str:
        return trans.ngettext("SERVICES_VIEW_COUNT_S {count}", "SERVICES_VIEW_COUNT_P {count}", count).format(count=count)

    def get_viewer_count_text(count: int) -> str:
        return trans.ngettext("SERVICES_VIEWER_COUNT_S {count}", "SERVICES_VIEWER_COUNT_P {count}", count).format(count=count)

    def get_stat_line(category_title: str, view_count: int, viewer_count: int) -> str:
        return f"<b>{category_title}:</b> {get_view_count_text(view_count)}, {get_viewer_count_text(viewer_count)}"

    category_stats = {}
    for stats in state.people_category_views_report(from_date):
        category_stats[stats.category.id] = get_stat_line(stats.category.title, stats.view_count, stats.viewer_count)

    if not category_stats:
        await reply(update, trans.gettext("ADMIN_MESSAGE_DM_STATS_EMPTY"), get_main_keyboard())
        return

    stats_header = trans.gettext("SERVICES_MESSAGE_DM_ADMIN_STATS_HEADER {from_date}")

    message = [stats_header.format(from_date=from_date.strftime("%Y-%m-%d")), ""]

    if -1 in category_stats.keys():
        message.append(category_stats[-1])
    for category in state.ServiceCategory.all():
        if category.id in category_stats.keys():
            message.append(category_stats[category.id])
        else:
            message.append(get_stat_line(category.title, 0, 0))

    if not settings.SERVICES_STATS_INCLUDE_ADMINISTRATORS:
        message.append("")
        message.append(trans.gettext("SERVICES_MESSAGE_DM_ADMIN_STATS_FOOTER_ADMINISTRATORS_EXCLUDED"))

    await reply(update, "\n".join(message), get_main_keyboard())


def register_handlers(application: Application, group: int):
    application.add_handler(CallbackQueryHandler(_handle_query, pattern=_ADMIN_EXPORT_DB), group=group)
    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(_handle_query, pattern=_ADMIN_IMPORT_DB)],
                            states={_ADMIN_UPLOADING_DB: [MessageHandler(filters.ATTACHMENT, _handle_received_db)]},
                            fallbacks=[]), group=group)
    application.add_handler(CallbackQueryHandler(_handle_query, pattern=_ADMIN_STATS), group=group)

    trans = i18n.default()
    register_buttons(((InlineKeyboardButton(trans.gettext("SERVICES_ADMIN_BUTTON_EXPORT_DB"),
                                            callback_data=_ADMIN_EXPORT_DB),
                       InlineKeyboardButton(trans.gettext("SERVICES_ADMIN_BUTTON_IMPORT_DB"),
                                            callback_data=_ADMIN_IMPORT_DB)), (
                          InlineKeyboardButton(trans.gettext("SERVICES_ADMIN_BUTTON_STATS"),
                                               callback_data=_ADMIN_STATS),)))
