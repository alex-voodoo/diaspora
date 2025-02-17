"""
Glossary
"""

import csv
import datetime
import io
import logging
import pathlib
import re
from collections import deque

from telegram import InlineKeyboardButton, Update
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

import settings
from common import i18n
from common.admin import get_main_keyboard, register_buttons
from common.log_time import LogTime
from common.messaging_helpers import self_destructing_reaction, self_destructing_reply
from settings import ADMINISTRATORS

TERMS_FILENAME = "glossary_terms.csv"
TERMS_FILE_PATH = pathlib.Path(__file__).parent / "resources" / TERMS_FILENAME

# Admin keyboard commands
ADMIN_DOWNLOAD_TERMS, ADMIN_UPLOAD_TERMS = "glossary-download-terms", "glossary-upload-terms"
ADMIN_UPLOADING_TERMS = 1

logger = logging.getLogger(__name__)

glossary_logger = logging.getLogger("glossary")
glossary_logging_handler = logging.FileHandler("glossary.log")
# noinspection SpellCheckingInspection
glossary_logging_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
glossary_logger.addHandler(glossary_logging_handler)
glossary_logger.propagate = False

# Glossary data.  Dictionary where key is a trigger word, and value is a dictionary with data associated with that
# trigger, all fields are strings:
# - standard: trigger in "native" language in its "best" form (properly transliterated, no typos or other errors)
# - original: word in "foreign" language
# - explanation: meaning of the term in the default language
glossary_data = None

# Triggers found recently.  Deque of dictionaries that have two fields: trigger is a trigger word that was found and
# timestamp is a moment when that happened.
recent_triggers: deque

commands = None

# Keys in dictionaries used in the above data structures.
TRIGGER, REGEX, STANDARD, ORIGINAL, EXPLANATION, TIMESTAMP = (
"trigger", "regex", "standard", "original", "explanation", "timestamp")


def get_file() -> io.BytesIO:
    """Return contents of the actual glossary terms file"""

    with open(TERMS_FILE_PATH, "rb") as inp:
        data = io.BytesIO(inp.read())
        return data


def set_file(data: io.BytesIO) -> bool:
    """Reset the glossary terms file with new contents"""

    data.seek(0)
    with open(TERMS_FILE_PATH, "wb") as out_file:
        out_file.write(data.read())

    global glossary_data

    # The new data will be loaded on the next call to `process_normal_message()`.
    glossary_data = None

    return True


def forget_old_triggers() -> None:
    """Remove recent triggers that are not recent enough"""

    global recent_triggers

    oldest_timestamp = datetime.datetime.now() - datetime.timedelta(seconds=settings.GLOSSARY_MAX_TRIGGER_AGE)
    while recent_triggers and recent_triggers[0][TIMESTAMP] < oldest_timestamp:
        recent_triggers.pop()


def format_explanations(terms: list) -> list:
    """Returns a list of strings that contain explanations for each trigger in `keys`"""

    result = []
    for term in terms:
        result.append("<b>{t}</b> <em>({o})</em> — {e}".format(e=term[EXPLANATION], o=term[ORIGINAL], t=term[STANDARD]))
    return result


async def process_normal_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search triggers in an incoming message, and react appropriately"""

    global glossary_data, recent_triggers

    if glossary_data is None:
        glossary_data = []
        with open(TERMS_FILE_PATH, encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                try:
                    regex, standard, original, explanation = row
                except Exception as e:
                    logger.warning(e)
                    continue
                glossary_data.append(
                    {REGEX: re.compile("\\b{}\\b".format(regex), re.IGNORECASE), STANDARD: standard, ORIGINAL: original,
                     EXPLANATION: explanation})
        logger.info("Loaded {} triggers for the glossary".format(len(glossary_data)))

    with LogTime("Trigger lookup", glossary_logger):
        filtered = []
        for term in glossary_data:
            try:
                if term[REGEX].search(update.effective_message.text) is not None:
                    filtered.append(term)
            except re.error as e:
                logger.warning("Exception raised while searching for regex \"{}\": {}".format(term, e))
    if not filtered:
        return

    forget_old_triggers()

    now = datetime.datetime.now()
    for trigger in filtered:
        recent_triggers.append({TIMESTAMP: now, TRIGGER: trigger})

    if settings.GLOSSARY_REPLY_TO_TRIGGER and len(filtered) >= settings.GLOSSARY_REPLY_TO_MIN_TRIGGER_COUNT:
        trans = i18n.default()

        text = [trans.gettext("GLOSSARY_TRIGGERED_EXPLANATION_HEADER")] + format_explanations(filtered)
        await self_destructing_reply(update, context, "\n".join(text), settings.GLOSSARY_REPLY_TO_TRIGGER_TIMEOUT,
                                     False)

    if settings.GLOSSARY_REACT_TO_TRIGGER:
        await self_destructing_reaction(update, context, [ReactionEmoji.EYES], settings.GLOSSARY_MAX_TRIGGER_AGE)


async def process_bot_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """React to mention

    If the mention does not contain any term recognised as a question to translate triggers noticed recently, sends "I
    do not understand this".  Otherwise, sends an explanation to triggers that stay currently in the global
    `recent_triggers` list, and clears that list, or says that there is nothing to explain.
    """

    trans = i18n.default()

    global commands

    if not commands:
        terms = (trans.gettext("GLOSSARY_TERM_TRANSLATE"), trans.gettext("GLOSSARY_TERM_EXPLAIN"),
                 trans.gettext("GLOSSARY_TERM_DECIPHER"), trans.gettext("GLOSSARY_TERM_GLOSSARY"))
        commands = [re.compile("\\b{}\\b".format(term), re.IGNORECASE) for term in terms]

    if not [command for command in commands if command.search(update.effective_message.text) is not None]:
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_UNKNOWN_TERM"), parse_mode=ParseMode.HTML)
        return

    global recent_triggers

    forget_old_triggers()

    if not recent_triggers:
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_EMPTY_CONTEXT"), parse_mode=ParseMode.HTML)
        return

    text = [trans.gettext("GLOSSARY_EXPLANATION_HEADER")] + format_explanations(
        [t for t in glossary_data if t[STANDARD] in sorted(list(set(t[TRIGGER][STANDARD] for t in recent_triggers)))])
    await update.effective_message.reply_text("\n".join(text), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    recent_triggers = deque()


async def handle_query_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> [None, int]:
    query = update.callback_query
    user = query.from_user

    if user.id not in ADMINISTRATORS.keys():
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == ADMIN_DOWNLOAD_TERMS:
        await user.send_document(get_file(), filename=TERMS_FILENAME, reply_markup=None)
    elif query.data == ADMIN_UPLOAD_TERMS:
        await query.message.reply_text(trans.gettext("GLOSSARY_MESSAGE_DM_ADMIN_REQUEST_TERMS"))

        return ADMIN_UPLOADING_TERMS


# noinspection PyUnusedLocal
async def handle_received_terms_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in ADMINISTRATORS.keys():
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return ConversationHandler.END

    trans = i18n.trans(user)

    document = update.message.effective_attachment

    if document.mime_type != "text/csv":
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_MESSAGE_DM_ADMIN_TERMS_WRONG_FILE_TYPE"),
                                                  reply_markup=get_main_keyboard())
        return ConversationHandler.END

    keywords_file = await document.get_file()
    data = io.BytesIO()
    await keywords_file.download_to_memory(data)

    if set_file(data):
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_MESSAGE_DM_ADMIN_TERMS_UPDATED"),
                                                  reply_markup=None)
    else:
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_MESSAGE_DM_ADMIN_TERMS_CANNOT_USE"),
                                                  reply_markup=get_main_keyboard())

    return ConversationHandler.END


def init(application: Application, group):
    """Prepare the feature as defined in the configuration"""

    if not settings.GLOSSARY_ENABLED:
        return

    global recent_triggers

    recent_triggers = deque()

    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(handle_query_admin, pattern=ADMIN_UPLOAD_TERMS)],
                            states={ADMIN_UPLOADING_TERMS: [
                                MessageHandler(filters.ATTACHMENT, handle_received_terms_file)]}, fallbacks=[]))
    application.add_handler(CallbackQueryHandler(handle_query_admin, pattern=ADMIN_DOWNLOAD_TERMS))

    trans = i18n.default()

    register_buttons(((InlineKeyboardButton(trans.gettext("GLOSSARY_BUTTON_DOWNLOAD_TERMS"),
                                            callback_data=ADMIN_DOWNLOAD_TERMS),
                       InlineKeyboardButton(trans.gettext("GLOSSARY_BUTTON_UPLOAD_TERMS"),
                                            callback_data=ADMIN_UPLOAD_TERMS)),))


def post_init(application: Application, group):
    """Post-init"""

    if not settings.GLOSSARY_ENABLED:
        return

    # The bot name is not yet known when init() is called, but the handler for mentions must be added before the handler
    # for all other messages, which is why we have to add handlers in post-init, when the bot is already created and
    # knows its own name.
    application.add_handler(MessageHandler(filters.Mention(application.bot.name), process_bot_mention), group=group)
    application.add_handler(MessageHandler(filters.TEXT & (~ filters.COMMAND), process_normal_message), group=group)
