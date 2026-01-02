"""
Admin functions of the Services feature
"""

import io
import json
import logging

from telegram import InlineKeyboardButton, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

from common import i18n
from common.admin import register_buttons
from common.checks import is_admin
from . import state

_ADMIN_EXPORT_DB, _ADMIN_IMPORT_DB = "services-admin-export-db", "services-admin-import-db"
_ADMIN_UPLOADING_DB = 1


async def _handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None | int:
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == _ADMIN_EXPORT_DB:
        services = {"categories": [category for category in state.people_category_select_all()],
                    "people": [person for person in state.people_select_all()]}
        await user.send_document(json.dumps(services, ensure_ascii=False, indent=2).encode("utf-8"),
                                 filename="services.json", reply_markup=None)
    elif query.data == _ADMIN_IMPORT_DB:
        await query.message.reply_text(trans.gettext("SERVICES_MESSAGE_DM_ADMIN_REQUEST_DB"))

        return _ADMIN_UPLOADING_DB


async def _handle_received_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return ConversationHandler.END

    document = update.message.effective_attachment

    db_file = await document.get_file()
    data = io.BytesIO()
    await db_file.download_to_memory(data)

    # TODO: Parse the file and import the DB
    trans = i18n.trans(user)
    await update.effective_message.reply_text(trans.gettext("SERVICES_MESSAGE_DM_ADMIN_DB_IMPORTED"), reply_markup=None)

    return ConversationHandler.END


def register_handlers(application: Application, group: int):
    application.add_handler(CallbackQueryHandler(_handle_query, pattern=_ADMIN_EXPORT_DB), group=group)
    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(_handle_query, pattern=_ADMIN_IMPORT_DB)],
                            states={_ADMIN_UPLOADING_DB: [
                                MessageHandler(filters.ATTACHMENT, _handle_received_db)]}, fallbacks=[]),
        group=group)

    trans = i18n.default()
    register_buttons(((InlineKeyboardButton(trans.gettext("SERVICES_ADMIN_BUTTON_EXPORT_DB"),
                                            callback_data=_ADMIN_EXPORT_DB),
                       InlineKeyboardButton(trans.gettext("SERVICES_ADMIN_BUTTON_IMPORT_DB"),
                                            callback_data=_ADMIN_IMPORT_DB)),))
