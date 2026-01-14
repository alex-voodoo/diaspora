"""
Admin functions of the Services feature
"""

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
        await user.send_document(json.dumps(state.export_db(), ensure_ascii=False, indent=2).encode("utf-8"),
                                 filename="services.json", reply_markup=None)
    elif query.data == _ADMIN_IMPORT_DB:
        await query.message.reply_text(trans.gettext("SERVICES_MESSAGE_DM_ADMIN_REQUEST_DB"))

        return _ADMIN_UPLOADING_DB


async def _handle_received_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    trans = i18n.trans(update.effective_user)

    success, error_message = has_attachment(update, "application/json")
    if not success:
        await message.reply_text(error_message, reply_markup=get_main_keyboard())
        return ConversationHandler.END

    db_file = await message.document.get_file()
    data = io.BytesIO()
    await db_file.download_to_memory(data)
    data.seek(0)

    try:
        data = json.load(data)
        schema = json.load(open(pathlib.Path(__file__).parent / "schema.json"))

        jsonschema.validate(data, schema)
        # TODO: Validate data integrity.

        state.import_db(data)

        await message.reply_text(trans.gettext("SERVICES_MESSAGE_DM_ADMIN_DB_IMPORTED"), reply_markup=None)
    except jsonschema.ValidationError as e:
        logging.error(e)
        await message.reply_text(trans.gettext("SERVICES_MESSAGE_DM_ADMIN_INVALID_JSON"),
                                 reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(e)
        await message.reply_text(trans.gettext("ADMIN_MESSAGE_DM_INTERNAL_ERROR"), reply_markup=get_main_keyboard())

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
