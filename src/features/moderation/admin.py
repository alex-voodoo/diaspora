"""
Admin functions of the Moderation feature
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
from common.bot import reply
from common.checks import is_admin
from . import state

_ADMIN_EXPORT_COMPLAINT_REASONS, _ADMIN_IMPORT_COMPLAINT_REASONS = (
    "moderation-admin-export-complaint-reasons", "moderation-admin-import-complaint-reasons")
_ADMIN_UPLOADING_COMPLAINT_REASONS = 1


async def _handle_query(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None | int:
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == _ADMIN_EXPORT_COMPLAINT_REASONS:
        await user.send_document(
            json.dumps(state.export_complaint_reasons(), ensure_ascii=False, indent=2).encode("utf-8"),
            filename="complaint_reasons.json", reply_markup=None)
    elif query.data == _ADMIN_IMPORT_COMPLAINT_REASONS:
        await reply(update, trans.gettext("MODERATION_MESSAGE_DM_ADMIN_REQUEST_COMPLAINT_REASONS"))

        return _ADMIN_UPLOADING_COMPLAINT_REASONS
    else:
        raise RuntimeError(f"Unknown action: {query.data}")


async def _handle_received_complaint_reasons(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
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
        schema = json.load(open(pathlib.Path(__file__).parent / "complaint_reasons_schema.json"))

        jsonschema.validate(data, schema)
        # TODO: Validate data integrity.

        state.import_complaint_reasons(data)

        await reply(update, trans.gettext("MODERATION_MESSAGE_DM_ADMIN_COMPLAINT_REASONS_IMPORTED"))
    except jsonschema.ValidationError as e:
        logging.error(e)
        await reply(update, trans.gettext("MODERATION_MESSAGE_DM_ADMIN_INVALID_JSON"), get_main_keyboard())
    except Exception as e:
        logging.error(e)
        await reply(update, trans.gettext("ADMIN_MESSAGE_DM_INTERNAL_ERROR"), get_main_keyboard())

    return ConversationHandler.END


def register_handlers(application: Application, group: int):
    application.add_handler(CallbackQueryHandler(_handle_query, pattern=_ADMIN_EXPORT_COMPLAINT_REASONS), group=group)
    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(_handle_query, pattern=_ADMIN_IMPORT_COMPLAINT_REASONS)],
                            states={_ADMIN_UPLOADING_COMPLAINT_REASONS: [
                                MessageHandler(filters.ATTACHMENT, _handle_received_complaint_reasons)]},
                            fallbacks=[]), group=group)

    trans = i18n.default()
    register_buttons(((InlineKeyboardButton(trans.gettext("MODERATION_ADMIN_BUTTON_EXPORT_COMPLAINT_REASONS"),
                                            callback_data=_ADMIN_EXPORT_COMPLAINT_REASONS),
                       InlineKeyboardButton(trans.gettext("MODERATION_ADMIN_BUTTON_IMPORT_COMPLAINT_REASONS"),
                                            callback_data=_ADMIN_IMPORT_COMPLAINT_REASONS)),))
