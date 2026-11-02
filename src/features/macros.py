"""
Send pre-defined messages (macros) to the main chat

Administrator only.

Adds a /macro command.

Sending a macro is a three-step process:
1. Issue the /macro command. The bot displays a list of available macros as a set of buttons.
2. Select a macro by pressing its button. The bot shows the message that is going to be sent and buttons to cancel or
   confirm sending it.
3. Confirm sending the macro by pressing the OK button. The bot will send the message to the main chat and report
   success, removing the buttons and thus terminating the command sequence.

After a macro is sent, MACROS_INTERVAL_MINUTES must pass before sending the next one.

The list of macros is configured via the administrator's interface (/admin command).
"""

import datetime
import gettext
import io
import logging
import re

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, filters,
                          MessageHandler)

from bot import talking_private
from common import admin, i18n
from common.admin import register_buttons, save_file_with_backup
from common.bot import reply, send
from common.checks import is_admin
from common.messaging_helpers import safe_delete_message
from common.settings import settings

_FILENAME = "macros.txt"
_FILE_PATH = settings.data_dir / _FILENAME

_COMMAND_MACRO = "macro"
_COMMAND_MACRO_CANCEL = "macro-cancel"
_COMMAND_MACRO_SELECT = "macro-select"
_COMMAND_MACRO_SELECT_CANCEL = "macro-select-cancel"
_COMMAND_MACRO_SEND = "macro-send"

_QUERY_FORMAT = "{command}:{index}"
_QUERY_RE = re.compile("^(macro-[-\\w]+):(\\d+)$")

(_ADMIN_DOWNLOAD, _ADMIN_UPLOAD) = ("macros-download", "macros-upload")
_ADMIN_UPLOADING = 1

(_MACRO_CAPTION, _MACRO_BODY) = ("caption", "body")

_macros = []
_last_macro_timestamp = datetime.datetime.now() - datetime.timedelta(minutes=settings.MACROS_INTERVAL_MINUTES)


def _load_macros():
    """Load macros from the file"""

    global _macros
    _macros = []

    try:
        with open(_FILE_PATH, encoding="utf-8") as f:
            current_macro = []
            current_caption = ""

            def submit_current_macro() -> None:
                global _macros
                nonlocal current_macro
                nonlocal current_caption

                if current_caption:
                    _macros.append({_MACRO_CAPTION: current_caption, _MACRO_BODY: "\n".join(current_macro).strip()})
                current_macro = []
                current_caption = ""

            for line in f.readlines():
                if line.startswith("#"):
                    submit_current_macro()
                    current_caption = line.strip("# \n")
                    continue

                current_macro.append(line)

            submit_current_macro()
    except FileNotFoundError:
        logging.info(f"{_FILE_PATH} was not found, creating a fresh file")
        with open(_FILE_PATH, "w") as f:
            f.write(i18n.default().gettext("MACROS_FILE_TEMPLATE"))
        _load_macros()

    logging.info(f"Loaded {len(_macros)} macros")


def _get_macros() -> io.BytesIO:
    """Return contents of the actual keywords file as a byte stream"""

    with open(_FILE_PATH, "rb") as inp:
        data = io.BytesIO(inp.read())
        return data


def _build_macros_keyboard(trans: gettext.GNUTranslations, cancel_command: str) -> InlineKeyboardMarkup | None:
    """Create a vertical keyboard with buttons for each defined macro and a cancel button in the bottom

    Each macro button uses caption of its macro as caption, and carries index of the macro in the global array as its
    callback data. The cancel button has generic Cancel caption and carries `cancel_command` as its callback data.
    """

    buttons = [(InlineKeyboardButton(_macros[index][_MACRO_CAPTION],
                                     callback_data=_QUERY_FORMAT.format(command=_COMMAND_MACRO_SELECT, index=index)),)
               for index in range(0, len(_macros))]
    if not buttons:
        return None

    buttons.append((InlineKeyboardButton(trans.gettext("GENERIC_BUTTON_CANCEL"),
                                         callback_data=cancel_command),))

    return InlineKeyboardMarkup(buttons)


async def _handle_received_macros(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save a macros definition file received from the user"""

    trans = i18n.trans(update.effective_user)

    if await save_file_with_backup(update, _FILE_PATH, "text/plain"):
        global _macros

        _macros = None
        _load_macros()

        await reply(update, trans.gettext("MACROS_MESSAGE_DM_ADMIN_FILE_UPDATED"))

    return ConversationHandler.END


async def _handle_query_admin(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> [None, int]:
    """Handle a query sent by buttons of the feature admin menu

    Admin menu buttons are "Upload macros" and "Download macros". Both are handled by this function.
    """

    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("fUser {username=user.username} is not listed as administrator!")
        return

    trans = i18n.trans(user)

    if query.data == _ADMIN_DOWNLOAD:
        await user.send_document(_get_macros(), filename=_FILENAME, reply_markup=None)
    elif query.data == _ADMIN_UPLOAD:
        await reply(update, trans.gettext("MACROS_MESSAGE_DM_ADMIN_REQUEST_FILE"))

        return _ADMIN_UPLOADING


async def _handle_command_macro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the list of macros

    This is the main entry point of the feature: it handles the command that will display the selection of available
    macros. The command must be issued by an administrator in the private channel. The list of macros must be non-empty,
    and enough time should have passed since a macro had been sent previously (see `MACROS_INTERVAL_MINUTES` setting).
    """

    message = update.effective_message
    user = message.from_user

    if not is_admin(user):
        logging.info(f"User {user.username} tried to run the /macro command")
        return

    if not await talking_private(update, context):
        await safe_delete_message(context, message.id, message.chat.id)

    trans = i18n.trans(update.effective_user)

    if not _macros:
        await send(context, user.id, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_NO_MACROS_DEFINED"))
        return
    if _last_macro_timestamp + datetime.timedelta(minutes=settings.MACROS_INTERVAL_MINUTES) > datetime.datetime.now():
        await send(context, user.id, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_WAIT"))
        return

    await send(context, user.id, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_SELECT_MACRO"),
               reply_markup=_build_macros_keyboard(trans, _COMMAND_MACRO_CANCEL))


async def _handle_command_macro_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel the /macro command sequence at the first step (selecting a macro to send)

    Edits the message to "Cancelled" and removes the buttons keyboard, thus terminating the command.
    """

    await update.callback_query.edit_message_text(
        i18n.trans(update.effective_user).gettext("MACROS_MESSAGE_DM_ADMIN_CANCELLED"))


async def _handle_macro_select_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel the /macro command sequence at the second step (confirming sending a macro selected previously)

    Edits the message to "Select macro" and shows the buttons for selecting macros, thus returning to step 1.
    """

    query = update.callback_query
    trans = i18n.trans(update.effective_user)
    await query.edit_message_text(trans.gettext("MACROS_MESSAGE_DM_ADMIN_SELECT_MACRO"))
    await query.edit_message_reply_markup(_build_macros_keyboard(trans, _COMMAND_MACRO_CANCEL))


async def _handle_macro_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle queries emerging in process of selecting and sending a macro

    The /macro command initiates a sequence of steps (see feature description in the file comment) where each step shows
    a menu, and buttons that proceed with previewing and sending a macro use the same pattern for callback data and are
    handled in this function. Cancel buttons have separate handlers.
    """

    query = update.callback_query

    command, index_str = _QUERY_RE.match(query.data).groups()
    index = int(index_str)

    trans = i18n.trans(update.effective_user)

    assert str(index) == index_str
    if index not in range(0, len(_macros)):
        await query.edit_message_text(trans.gettext("MACROS_MESSAGE_DM_ADMIN_INDEX_ERROR"))
        return

    if command == _COMMAND_MACRO_SELECT:
        context.user_data["admin-macros-current-selection"] = {"index": index, "macro": _macros[index]}

        await query.edit_message_text(trans.gettext("MACROS_MESSAGE_DM_ADMIN_MACRO_PREVIEW {body} {caption}").format(
            body=_macros[index][_MACRO_BODY], caption=_macros[index][_MACRO_CAPTION]))
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup([(InlineKeyboardButton(trans.gettext("GENERIC_BUTTON_CANCEL"),
                                                        callback_data=_COMMAND_MACRO_SELECT_CANCEL),
                                   InlineKeyboardButton(trans.gettext("GENERIC_BUTTON_OK"),
                                                        callback_data=_QUERY_FORMAT.format(
                                                            command=_COMMAND_MACRO_SEND, index=index)))]))
    elif command == _COMMAND_MACRO_SEND:
        assert index == context.user_data["admin-macros-current-selection"]["index"]
        macro = context.user_data["admin-macros-current-selection"]["macro"]
        await send(context, settings.MAIN_CHAT_ID, macro[_MACRO_BODY])
        await query.edit_message_text(trans.gettext("MACROS_MESSAGE_DM_ADMIN_MACRO_SENT {caption}").format(
            caption=macro[_MACRO_CAPTION]))

        del context.user_data["admin-macros-current-selection"]
        global _last_macro_timestamp
        _last_macro_timestamp = datetime.datetime.now()
    else:
        raise RuntimeError(f"Unknown command {command}")


def init(application: Application, group):
    """Prepare the feature as defined in the configuration"""

    if not settings.MACROS_ENABLED:
        return

    trans = i18n.default()

    # Register admin handlers
    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(_handle_query_admin, pattern=_ADMIN_UPLOAD)],
                            states={_ADMIN_UPLOADING: [
                                MessageHandler(filters.ATTACHMENT, _handle_received_macros)]}, fallbacks=[]),
        group=group)

    application.add_handler(CallbackQueryHandler(_handle_query_admin, pattern=_ADMIN_DOWNLOAD), group=group)

    application.add_handler(CommandHandler(_COMMAND_MACRO, _handle_command_macro), group=group)
    application.add_handler(CallbackQueryHandler(_handle_command_macro_cancel, pattern=_COMMAND_MACRO_CANCEL),
                            group=group)

    application.add_handler(CallbackQueryHandler(_handle_macro_query, pattern=_QUERY_RE), group=group)
    application.add_handler(CallbackQueryHandler(_handle_macro_select_cancel,
                                                 pattern=_COMMAND_MACRO_SELECT_CANCEL), group=group)

    register_buttons(((InlineKeyboardButton(trans.gettext("MACROS_BUTTON_DOWNLOAD"), callback_data=_ADMIN_DOWNLOAD),
                       InlineKeyboardButton(trans.gettext("MACROS_BUTTON_UPLOAD"), callback_data=_ADMIN_UPLOAD)),))

    _load_macros()


def post_init(_application: Application, _group: int):
    """Post-init"""

    if not settings.MACROS_ENABLED:
        return

    trans = i18n.default()

    if not admin.feature_commands:
        admin.feature_commands = []

    admin.feature_commands.append(
        BotCommand(command=_COMMAND_MACRO, description=trans.gettext("MACRO_COMMAND_DESCRIPTION")))
