"""
Admin utilities
"""

import io
import os.path
import shutil
from collections.abc import Callable
from pathlib import Path

from telegram import InlineKeyboardMarkup, Update

from . import i18n
from .bot import reply
from .checks import is_admin

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

    return InlineKeyboardMarkup(buttons if buttons else [])


def has_attachment(update: Update, mime_type: str) -> (bool, str):
    """Check if `update` has an attachment, optionally if that attachment has the specified MIME type

    Helper function for admin functions that want to process files of certain types.  Returns True only if the current
    user is administrator, and the update has an attachment.  Optionally (if `mime_type` is not empty) ensures that the
    attachment has that MIME type.  Otherwise, returns False and a message that explains the problem.
    """

    assert is_admin(update.effective_user), "common.admin.has_attachment() is called for a non-administrator user!"

    trans = i18n.trans(update.effective_user)

    if not hasattr(update.effective_message, "document") or not update.effective_message.document:
        return False, trans.gettext("ADMIN_MESSAGE_DM_EXPECTED_REGULAR_FILE")

    document = update.effective_message.document

    if mime_type and document.mime_type != mime_type:
        return False, trans.gettext("ADMIN_MESSAGE_DM_UNEXPECTED_FILE_TYPE {expected} {actual}").format(
            actual=document.mime_type, expected=mime_type)

    return True, ""


async def save_file_with_backup(update: Update, path: Path, expected_mime_type: str = None,
                                validate: Callable[[io.BytesIO], (bool, str)] = None) -> bool:
    """Save a file uploaded by an administrator, backing up the current version

    Returns whether a new version was saved.

    `validate` must be a callable that accepts file data as `io.BytesIO` and returns a tuple of a boolean and a string.
    If provided, should ensure that the new data could be accepted as new contents for the file without actually
    changing any files or run-time state of the bot.  The boolean indicates success, and the string contains an error
    message for the case when the validation failed.
    """

    trans = i18n.trans(update.effective_user)

    success, error_message = has_attachment(update, expected_mime_type)
    if not success:
        await reply(update, error_message, reply_markup=get_main_keyboard())
        return False

    file = await update.effective_message.document.get_file()
    data = io.BytesIO()
    await file.download_to_memory(data)
    data.seek(0)

    if validate:
        success, message = validate(data)
        if not success:
            await reply(update,
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
        await reply(update,
                    trans.gettext("ADMIN_MESSAGE_DM_OS_ERROR_WHILE_SAVING {error}".format(error=e)),
                    get_main_keyboard())
        return False

    return True
