"""
Admin utilities
"""
import io
import logging
import os.path
import shutil
from collections.abc import Callable
from pathlib import Path

from telegram import InlineKeyboardMarkup, Update

import settings
from common import i18n

buttons = None


def register_buttons(row) -> None:
    """Register one or more rows of buttons in the main administrator's keyboard"""

    global buttons

    if not buttons:
        buttons = []

    buttons += row


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Return main administrator's keyboard

    The keyboard is built based on the global `buttons` sequence prepared at init time with calls to `register_button()`
    from the core module and features.
    """

    global buttons

    return InlineKeyboardMarkup(buttons)


async def save_file_with_backup(update: Update, path: Path, expected_mime_type: str = None,
                                validate: Callable[[io.BytesIO], (bool, str)] = None) -> bool:
    """Saves a file uploaded by an administrator, backing up the current version

    Returns whether a new version was saved.

    `validate` must be a callable that accepts file data as `io.BytesIO` and returns a tuple of a boolean and a string.
    If provided, should ensure that the new data could be accepted as new contents for the file without actually
    changing any files or run-time state of the bot.  The boolean indicates success, and the string contains an error
    message for the case when the validation failed.
    """

    if update.effective_user.id not in settings.ADMINISTRATORS.keys():
        logging.error("common.admin.save_file_with_backup() is called for a non-administrator user!")
        return False

    trans = i18n.trans(update.effective_user)

    if not hasattr(update.effective_message, "document") or not update.effective_message.document:
        await update.effective_message.reply_text(trans.gettext("ADMIN_MESSAGE_DM_EXPECTED_REGULAR_FILE"),
            reply_markup=get_main_keyboard())
        return False

    try:
        document = update.effective_message.document

        if expected_mime_type and document.mime_type != expected_mime_type:
            await update.effective_message.reply_text(
                trans.gettext("ADMIN_MESSAGE_DM_UNEXPECTED_FILE_TYPE {expected} {actual}").format(
                    actual=document.mime_type, expected=expected_mime_type), reply_markup=get_main_keyboard())
            return False
    except Exception as e:
        logging.error(e)
        await update.effective_message.reply_text(trans.gettext("ADMIN_MESSAGE_DM_INTERNAL_ERROR"),
            reply_markup=get_main_keyboard())
        return False

    file = await document.get_file()
    data = io.BytesIO()
    await file.download_to_memory(data)
    data.seek(0)

    if validate:
        success, message = validate(data)
        if not success:
            await update.effective_message.reply_text(
                trans.gettext("ADMIN_MESSAGE_DM_VALIDATION_FAILED {message}").format(message=message),
                reply_markup=get_main_keyboard())
            return False

    try:
        backup_path = path.with_suffix(".backup")
        backup_backup_path = ""

        if os.path.exists(path):
            if os.path.exists(backup_path):
                backup_backup_path = backup_path.with_suffix(".backup.backup")
                shutil.move(backup_path, backup_backup_path)

            shutil.move(path, backup_path)

        data.seek(0)
        with open(path, "wb") as out_file:
            out_file.write(data.read())

        if backup_backup_path and os.path.exists(backup_backup_path):
            os.remove(backup_backup_path)
    except OSError as e:
        await update.effective_message.reply_text(
            trans.gettext("ADMIN_MESSAGE_DM_OS_ERROR_WHILE_SAVING {error}".format(error=e)),
            reply_markup=get_main_keyboard())
        return False

    return True
