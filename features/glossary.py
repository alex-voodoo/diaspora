"""
Glossary
"""

import csv
import datetime
import logging
import pathlib
from collections import deque

from pymystem3 import Mystem
from telegram import Update
from telegram.constants import ReactionEmoji, ParseMode
from telegram.ext import Application, ContextTypes, filters, MessageHandler

import settings
from common import i18n
from common.messaging_helpers import self_destructing_reply, self_destructing_reaction

TERMS_FILE_PATH = pathlib.Path(__file__).parent / "resources" / "glossary_terms.csv"

logger = logging.getLogger(__name__)

# Glossary data.  Dictionary where key is a trigger word, and value is a dictionary with data associated with that
# trigger, all fields are strings:
# - standard: trigger in "native" language in its "best" form (properly transliterated, no typos or other errors)
# - original: word in "foreign" language
# - explanation: meaning of the term in the default language
glossary_data = None

# Triggers found recently.  Deque of dictionaries that have two fields: trigger is a trigger word that was found and
# timestamp is a moment when that happened.
recent_triggers: deque

# Keys in dictionaries used in the above data structures.
TRIGGER, STANDARD, ORIGINAL, EXPLANATION, TIMESTAMP = ("trigger", "standard", "original", "explanation", "timestamp")

lemmatizer = Mystem()


def collapse_recent_triggers():
    """Remove recent triggers that are not recent enough"""

    global recent_triggers

    oldest_timestamp = datetime.datetime.now() - datetime.timedelta(seconds=settings.GLOSSARY_MAX_TRIGGER_AGE)
    while recent_triggers and recent_triggers[0][TIMESTAMP] < oldest_timestamp:
        recent_triggers.pop()


def format_explanations(keys: list) -> list:
    """Returns a list of strings that contain explanations for each trigger in `keys`"""

    result = []
    for trigger in keys:
        result.append("<b>{t}</b> <em>({o})</em> — {e}".format(e=glossary_data[trigger][EXPLANATION],
                                                               o=glossary_data[trigger][ORIGINAL],
                                                               t=glossary_data[trigger][STANDARD]))
    return result


async def process_normal_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search triggers in an incoming message, and react appropriately"""

    global glossary_data, recent_triggers

    if glossary_data is None:
        logger.info("Loading triggers for the glossary")
        glossary_data = {}
        with open(TERMS_FILE_PATH, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                try:
                    term, standard, original, explanation = row
                except Exception as e:
                    logger.warning(e)
                    continue
                glossary_data[term.lower()] = {STANDARD: standard, ORIGINAL: original, EXPLANATION: explanation}

    filtered = [term for term in glossary_data.keys() if term in lemmatizer.lemmatize(update.effective_message.text)]
    if not filtered:
        return

    collapse_recent_triggers()

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

    terms = (trans.gettext("GLOSSARY_TERM_TRANSLATE"), trans.gettext("GLOSSARY_TERM_EXPLAIN"),
             trans.gettext("GLOSSARY_TERM_DECIPHER"), trans.gettext("GLOSSARY_TERM_GLOSSARY"))

    if not [term for term in terms if term in lemmatizer.lemmatize(update.effective_message.text)]:
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_UNKNOWN_TERM"), parse_mode=ParseMode.HTML)
        return

    global recent_triggers

    collapse_recent_triggers()

    if not recent_triggers:
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_EMPTY_CONTEXT"), parse_mode=ParseMode.HTML)
        return

    text = [trans.gettext("GLOSSARY_EXPLANATION_HEADER")] + format_explanations(
        sorted(list(set([t[TRIGGER] for t in recent_triggers]))))
    await update.effective_message.reply_text("\n".join(text), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    recent_triggers = deque()


def init(application: Application, group):
    """Prepare the feature as defined in the configuration"""

    if not settings.GLOSSARY_ENABLED:
        return

    global recent_triggers

    recent_triggers = deque()


def post_init(application: Application, group):
    """Post-init"""

    if not settings.GLOSSARY_ENABLED:
        return

    # The bot name is not yet known when init() is called, but the handler for mentions must be added before the handler
    # for all other messages, which is why we have to add handlers in post-init, when the bot is already created and
    # knows its own name.
    application.add_handler(MessageHandler(filters.Mention(application.bot.name), process_bot_mention), group=group)
    application.add_handler(MessageHandler(filters.TEXT & (~ filters.COMMAND), process_normal_message), group=group)
