"""
Standard responses
"""

import datetime
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
_COMMAND_MACRO_EXEC = "macros-exec:{}"
_COMMAND_MACRO_EXEC_RE = "^macros-exec:[0-9]+$"

(_ADMIN_DOWNLOAD, _ADMIN_UPLOAD) = ("macros-download", "macros-upload")
_ADMIN_UPLOADING = 1

(_MACRO_CAPTION, _MACRO_BODY) = ("caption", "body")

_macros = []
_last_macro_timestamp = datetime.datetime.now() - datetime.timedelta(minutes=settings.MACROS_INTERVAL_MINUTES)


def _load_macros():
    """Loads macros if they are not yet loaded"""

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
                    # noinspection PyUnresolvedReferences
                    _macros.append({_MACRO_CAPTION: current_caption, _MACRO_BODY: "\n".join(current_macro)})
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
        logging.info(f"{_FILE_PATH} was not found, trying to create it")
        with open(_FILE_PATH, "w") as f:
            f.write("This file defines macros that the bot can send.\n"
                    "\n"
                    "A definition of a macro starts with a line that begins with #, that line is used as a title of "
                    "the button that will send the macro. Everything that goes below the header is the body of the "
                    "macro.\n"
                    "\n"
                    "The macros are sent verbatim using HTML parse mode, and support limited subset of HTML tags: <a>, "
                    "<b>, <strong>, <i>, <em>, <u>, <ins>, <s>, <strike>, <code>, <pre>.\n"
                    "\n"
                    "This text goes before the first macro header and is ignored by the bot. See an example of a "
                    "macro just below this line.\n"
                    "\n"
                    "# Say hello\n"
                    "\n"
                    "Hello everyone!  I help people in this group. Talk to me in private to see what I can do, and "
                    "also check out <a href=\"https://github.com/alex-voodoo/diaspora\">my source code</a>, it is open "
                    "and free!")
        _load_macros()

    logging.info(f"Loaded {len(_macros)} macros")


def _get_macros() -> io.BytesIO:
    """Return contents of the actual keywords file"""

    with open(_FILE_PATH, "rb") as inp:
        data = io.BytesIO(inp.read())
        return data


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
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("fUser {username=user.username} is not listed as administrator!")
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == _ADMIN_DOWNLOAD:
        await user.send_document(_get_macros(), filename=_FILENAME, reply_markup=None)
    elif query.data == _ADMIN_UPLOAD:
        await reply(update, trans.gettext("MACROS_MESSAGE_DM_ADMIN_REQUEST_FILE"))

        return _ADMIN_UPLOADING


async def _handle_command_macro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the admin menu"""

    message = update.effective_message
    user = message.from_user

    if not is_admin(user):
        logging.info(f"User {user.username} tried to run the /macro command")
        return

    if not await talking_private(update, context):
        await safe_delete_message(context, message.id, message.chat.id)

    global _macros, _last_macro_timestamp
    trans = i18n.trans(update.effective_user)

    if _last_macro_timestamp + datetime.timedelta(minutes=settings.MACROS_INTERVAL_MINUTES) > datetime.datetime.now():
        await send(context, user.id, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_WAIT"))
        return

    buttons = [(InlineKeyboardButton(_macros[index][_MACRO_CAPTION], callback_data=_COMMAND_MACRO_EXEC.format(index)),)
               for index in range(0, len(_macros))]
    if not buttons:
        await send(context, user.id, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_NO_MACROS_DEFINED"))
        return

    await send(context, user.id, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_SELECT_MACRO"),
               reply_markup=InlineKeyboardMarkup(buttons))


async def _handle_macro_exec(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.edit_message_reply_markup(None)

    command, index = query.data.split(":")
    index = int(index)

    global _macros
    if index not in range(0, len(_macros)):
        logging.error("Index out of range")
        return

    trans = i18n.trans(update.effective_user)

    await send(context, settings.MAIN_CHAT_ID, _macros[index][_MACRO_BODY])
    await reply(update, text=trans.gettext("MACROS_MESSAGE_DM_ADMIN_MACRO_SENT {caption}").format(
        caption=_macros[index][_MACRO_CAPTION]))

    global _last_macro_timestamp
    _last_macro_timestamp = datetime.datetime.now()


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
    application.add_handler(CallbackQueryHandler(_handle_macro_exec, pattern=re.compile(_COMMAND_MACRO_EXEC_RE)),
                            group=group)

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
