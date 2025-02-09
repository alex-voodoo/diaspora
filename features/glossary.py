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

triggers = None
lemmatizer = Mystem()
recent_triggers: deque


def collapse_recent_triggers():
    """Remove recent triggers that are not recent enough"""

    global recent_triggers

    oldest_timestamp = datetime.datetime.now() - datetime.timedelta(seconds=settings.GLOSSARY_MAX_TRIGGER_AGE)
    while recent_triggers and recent_triggers[0]["timestamp"] < oldest_timestamp:
        recent_triggers.pop()


def format_explanations(keys: list) -> list:
    """Returns a list of strings that contain explanations for each trigger in `keys`"""

    result = []
    for trigger in keys:
        result.append("<b>{t}</b> <em>({o})</em> — {e}".format(e=triggers[trigger]["explanation"],
                                                               o=triggers[trigger]["original"], t=trigger))
    return result


async def process_normal_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search triggers in an incoming message, and react appropriately"""

    global triggers, recent_triggers

    if triggers is None:
        logger.info("Loading triggers for the glossary")
        triggers = {}
        with open(TERMS_FILE_PATH) as f:
            reader = csv.reader(f)
            for row in reader:
                term, original, explanation = row
                triggers[term] = {"original": original, "explanation": explanation}

    filtered = [term for term in triggers.keys() if term in lemmatizer.lemmatize(update.effective_message.text)]
    if not filtered:
        return

    collapse_recent_triggers()

    now = datetime.datetime.now()
    for trigger in filtered:
        recent_triggers.append({"timestamp": now, "trigger": trigger})

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
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_UNKNOWN_TERM"))
        return

    global recent_triggers

    collapse_recent_triggers()

    if not recent_triggers:
        await update.effective_message.reply_text(trans.gettext("GLOSSARY_EMPTY_CONTEXT"))
        return

    text = [trans.gettext("GLOSSARY_EXPLANATION_HEADER")] + format_explanations(
        sorted(list(set([t["trigger"] for t in recent_triggers]))))
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
