"""
Glossary
"""

import csv
import datetime
import io
import logging
import re
import unicodedata
from collections import deque

from telegram import InlineKeyboardButton, Update
from telegram.constants import ReactionEmoji
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, ConversationHandler, filters, MessageHandler

from common import i18n, settings
from common.admin import register_buttons, save_file_with_backup
from common.bot import reply
from common.checks import is_admin
from common.log import LogTime
from common.messaging_helpers import self_destructing_reaction, self_destructing_reply
from common.settings import settings

TERMS_FILENAME = "glossary_terms.csv"
TERMS_FILE_PATH = settings.data_dir / TERMS_FILENAME

# Admin keyboard commands
ADMIN_DOWNLOAD_TERMS, ADMIN_UPLOAD_TERMS = "glossary-download-terms", "glossary-upload-terms"
ADMIN_UPLOADING_TERMS = 1

# Glossary data.  List of dictionary items with the following fields:
# - regex: regular expression that should capture the trigger in a message in any form, including misspellings
# - standard: trigger in "native" language in its "best" form (properly transliterated, no typos or other errors)
# - original: word in its original ("foreign") language
# - explanation: meaning of the term in the default language
glossary_data = None

# Triggers found recently.  Deque of dictionaries that have two fields: trigger is a glossary term that was found and
# timestamp is a moment when that happened.
recent_triggers: deque

# Commands given to the bot via mentioning it.
mention_commands: dict

# Keys in dictionaries used in the above data structures.
TRIGGER, REGEX, STANDARD, STANDARD_STRIPPED, ORIGINAL, EXPLANATION, TIMESTAMP = (
    "trigger", "regex", "standard", "standard-stripped", "original", "explanation", "timestamp")
COMMAND_EXPLAIN, COMMAND_WHATISIT = "explain", "whatisit"


def damerau_levenshtein_distance(one: str, two: str) -> int:
    """Calculate the Damerau-Levenshtein distance between two strings

    Source: https://github.com/TheAlgorithms/Python/blob/master/strings/damerau_levenshtein_distance.py (reformatted)
    """

    # Create a dynamic programming matrix to store the distances
    dp_matrix = [[0] * (len(two) + 1) for _ in range(len(one) + 1)]

    # Initialize the matrix
    for i in range(len(one) + 1):
        dp_matrix[i][0] = i
    for j in range(len(two) + 1):
        dp_matrix[0][j] = j

    # Fill the matrix
    for i, first_char in enumerate(one, start=1):
        for j, second_char in enumerate(two, start=1):
            cost = int(first_char != second_char)

            dp_matrix[i][j] = min(dp_matrix[i - 1][j] + 1,  # Deletion
                                  dp_matrix[i][j - 1] + 1,  # Insertion
                                  dp_matrix[i - 1][j - 1] + cost,  # Substitution
                                  )

            if i > 1 and j > 1 and one[i - 1] == two[j - 2] and one[i - 2] == two[j - 1]:
                # Transposition
                dp_matrix[i][j] = min(dp_matrix[i][j], dp_matrix[i - 2][j - 2] + cost)

    return dp_matrix[-1][-1]


def maybe_load_glossary_data():
    """Loads glossary if it is not yet loaded"""

    global glossary_data
    if glossary_data is not None:
        return

    def strip_diacritics(term: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', term) if unicodedata.category(c) != 'Mn')

    glossary_data = []
    with open(TERMS_FILE_PATH, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            try:
                regex, standard, original, explanation = row
            except Exception as e:
                logging.warning(e)
                continue
            glossary_data.append(
                {REGEX: re.compile("\\b{}\\b".format(regex.strip()), re.IGNORECASE), STANDARD: standard.strip(),
                 ORIGINAL: original.strip(), EXPLANATION: explanation.strip(),
                 STANDARD_STRIPPED: strip_diacritics(standard.strip())})
    logging.info("Loaded {} triggers for the glossary".format(len(glossary_data)))


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

    if len(terms) > 1 and settings.GLOSSARY_EXTERNAL_URL:
        result.append(
            i18n.default().gettext("GLOSSARY_EXTERNAL_URL_NOTE {url}").format(url=settings.GLOSSARY_EXTERNAL_URL))

    return result


async def process_normal_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search triggers in an incoming message, and react appropriately"""

    global glossary_data, recent_triggers

    if not update.message:
        logging.info("Skipping an update that does not have a message.")
        return

    maybe_load_glossary_data()

    with LogTime("Trigger lookup"):
        filtered = []
        for term in glossary_data:
            try:
                if term[REGEX].search(update.effective_message.text) is not None:
                    filtered.append(term)
            except re.error as e:
                logging.warning("Exception raised while searching for regex \"{}\": {}".format(term, e))
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


async def maybe_process_command_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Try to find the "explain" command in the message, and handle it if found

    Tries to find one of command terms that mean "explain the current context", and if found, renders the explanation
    for all recent triggers, then clears them.

    Returns whether the command term was found.
    """

    global mention_commands

    if mention_commands[COMMAND_EXPLAIN].search(update.effective_message.text) is None:
        return False

    global recent_triggers

    forget_old_triggers()

    trans = i18n.default()

    if not recent_triggers:
        await reply(update, trans.gettext("GLOSSARY_EMPTY_CONTEXT"))
        return True

    text = [trans.gettext("GLOSSARY_EXPLANATION_HEADER")] + format_explanations(
        [t for t in glossary_data if t[STANDARD] in sorted(list(set(t[TRIGGER][STANDARD] for t in recent_triggers)))])
    await reply(update, "\n".join(text))

    recent_triggers = deque()
    return True


async def maybe_process_command_whatisit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Try to find the "what is ..." command in the message, and handle it if found

    Tries to find a pattern that means "what is <word>", and if found, tries to find that term and respond with an
    explanation.

    Returns whether the command term was found.
    """

    trans = i18n.default()

    match = mention_commands[COMMAND_WHATISIT].search(update.effective_message.text)
    if match is None:
        return False

    word = match.group("term")

    for term in glossary_data:
        if term[STANDARD_STRIPPED] == word:
            await reply(update, format_explanations([term])[0])
            return True

    possible_terms = []
    for term in glossary_data:
        if abs(len(word) - len(term[STANDARD_STRIPPED])) > 2:
            continue
        if damerau_levenshtein_distance(word, term[STANDARD_STRIPPED]) <= 2:
            possible_terms.append(term)

    if possible_terms:
        if len(possible_terms) > 1:
            text = [trans.gettext("GLOSSARY_WHATISIT_FUZZY_MATCH")] + format_explanations(possible_terms)
            await reply(update, "\n".join(text))
        else:
            await reply(update, format_explanations(possible_terms)[0])
        return True

    await reply(update, trans.gettext("GLOSSARY_I_DO_NOT_KNOW"))
    return True


async def process_bot_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """React to mention

    The update text must start with the handle of the bot, otherwise it is ignored.  This is to handle commands like
    "@OurBot, what is this" and skip things like "Everyone, use @OurBot for fun stuff".

    If the mention does not contain any term recognised as a question to translate triggers noticed recently, sends "I
    do not understand this".  Otherwise, sends an explanation to triggers that stay currently in the global
    `recent_triggers` list, and clears that list, or says that there is nothing to explain.
    """

    if not update.effective_message.text.startswith(context.bot.name):
        return

    maybe_load_glossary_data()

    trans = i18n.default()

    # TODO find a way to register multiple mention commands from different features in the single handler in the core,
    # so that the only handler there would pick the mention and then dispatch it to the actual handlers.
    for handler in (maybe_process_command_explain, maybe_process_command_whatisit):
        if await handler(update, context):
            return

    if settings.GLOSSARY_EXTERNAL_URL:
        await reply(update, trans.gettext("GLOSSARY_UNKNOWN_COMMAND {url}").format(url=settings.GLOSSARY_EXTERNAL_URL))
    else:
        await reply(update, trans.gettext("GLOSSARY_UNKNOWN_COMMAND"))


async def handle_query_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> [None, int]:
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == ADMIN_DOWNLOAD_TERMS:
        await user.send_document(get_file(), filename=TERMS_FILENAME, reply_markup=None)
    elif query.data == ADMIN_UPLOAD_TERMS:
        await reply(update, trans.gettext("GLOSSARY_MESSAGE_DM_ADMIN_REQUEST_TERMS"))

        return ADMIN_UPLOADING_TERMS


# noinspection PyUnusedLocal
async def handle_received_terms_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trans = i18n.trans(update.effective_user)

    if await save_file_with_backup(update, TERMS_FILE_PATH, "text/csv"):
        global glossary_data

        # The new data will be loaded on the next call to `process_normal_message()`.
        glossary_data = None

        await reply(update, trans.gettext("GLOSSARY_MESSAGE_DM_ADMIN_TERMS_UPDATED"))

    return ConversationHandler.END


def init(application: Application, group):
    """Prepare the feature as defined in the configuration"""

    if not settings.GLOSSARY_ENABLED:
        return

    global recent_triggers

    recent_triggers = deque()

    trans = i18n.default()

    # Prepare regular expressions for the mention commands
    global mention_commands

    mention_commands = {
        COMMAND_EXPLAIN: re.compile("\\b{}\\b".format(trans.gettext("GLOSSARY_COMMAND_EXPLAIN")), re.IGNORECASE),
        COMMAND_WHATISIT: re.compile("\\b{}\\b".format(trans.gettext("GLOSSARY_COMMAND_WHATISIT")), re.IGNORECASE)}

    # Register admin handlers
    application.add_handler(
        ConversationHandler(entry_points=[CallbackQueryHandler(handle_query_admin, pattern=ADMIN_UPLOAD_TERMS)],
                            states={ADMIN_UPLOADING_TERMS: [
                                MessageHandler(filters.ATTACHMENT, handle_received_terms_file)]}, fallbacks=[]),
        group=group)
    application.add_handler(CallbackQueryHandler(handle_query_admin, pattern=ADMIN_DOWNLOAD_TERMS), group=group)

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
