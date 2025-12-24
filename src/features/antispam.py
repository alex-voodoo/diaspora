"""
Antispam
"""

import io
import json
import logging
import string

import joblib
import numpy as np
import telegram
from openai import OpenAI
from telegram import InlineKeyboardButton, Update
from telegram.ext import Application, CallbackQueryHandler, ConversationHandler, ContextTypes, filters, MessageHandler

from common import db, i18n
from common.admin import get_main_keyboard, register_buttons, save_file_with_backup
from common.checks import is_admin
from common.messaging_helpers import delete_message, safe_delete_message
from common.settings import settings


KEYWORDS_FILENAME = "antispam_keywords.txt"
KEYWORDS_FILE_PATH = settings.data_dir / KEYWORDS_FILENAME

OPENAI_FILE_PATH = settings.data_dir / "antispam_openai.joblib"

# Admin keyboard commands
(ADMIN_DOWNLOAD_SPAM, ADMIN_DOWNLOAD_KEYWORDS, ADMIN_UPLOAD_KEYWORDS, ADMIN_UPLOAD_OPENAI) = (
    "antispam-download-spam", "antispam-download-keywords", "antispam-upload-keywords", "antispam-upload-openai")
ADMIN_UPLOADING_KEYWORDS, ADMIN_UPLOADING_OPENAI = range(2)

logger = logging.getLogger(__name__)

keywords = None
openai_model = None


def detect_keywords(text: str) -> bool:
    """Detect spam using keywords"""

    global keywords

    if keywords is None:
        logger.info("Loading the list of keywords")
        keywords = []
        with open(KEYWORDS_FILE_PATH) as f:
            for line in f.readlines():
                keywords.append(line.strip())

    text_processed = [word.strip(string.punctuation) for word in text.lower().split()]

    result = any([bad_kw in text_processed for bad_kw in keywords])
    logger.info("Keywords found: {result}".format(result=result))

    return result


def get_keywords() -> io.BytesIO:
    """Return contents of the actual keywords file"""

    with open(KEYWORDS_FILE_PATH, "rb") as inp:
        data = io.BytesIO(inp.read())
        return data


def detect_emojis(message: telegram.Message) -> bool:
    """Detect spam that uses custom emojis"""

    if not hasattr(message, "entities"):
        return False

    custom_emoji_count = 0
    for e in message.entities:
        if e.type == telegram.MessageEntity.CUSTOM_EMOJI:
            custom_emoji_count += 1
            if custom_emoji_count > settings.ANTISPAM_EMOJIS_MAX_CUSTOM_EMOJI_COUNT:
                return True
    return False


def detect_openai(text: str) -> float:
    """Detect spam using the OpenAI model

    Return whether the confidence has been over `OPENAI_CONFIDENCE_THRESHOLD`
    """

    global openai_model

    # Load the model using joblib
    if openai_model is None:
        logger.info("Loading the OpenAI model")
        openai_model = joblib.load(OPENAI_FILE_PATH)

    # embedding
    client = OpenAI(api_key=settings.ANTISPAM_OPENAI_API_KEY)

    response = client.embeddings.create(input=text, model="text-embedding-3-small")
    embedding = response.data[0].embedding

    # Ensure the embedding is reshaped or adjusted as necessary based on how the model was trained
    embedding = np.array(embedding).reshape(1, -1)  # Reshape for a single sample prediction
    # Predict using the SVM model
    prediction = openai_model.predict_proba(embedding)

    return prediction[0][1]


def save_new_openai(data: io.BytesIO) -> bool:
    """Tries to load the new OpenAI model from `data`

    Returns whether it could load the new model.  On failure, the existing model is preserved.
    """

    data.seek(0)
    # noinspection PyBroadException
    try:
        new_model = joblib.load(data)
    except Exception:
        return False

    global openai_model

    openai_model = new_model

    data.seek(0)
    with open(OPENAI_FILE_PATH, "wb") as out_file:
        out_file.write(data.read())

    return True


def is_spam(message: telegram.Message) -> bool:
    """Evaluates `text` and returns whether it looks like spam

    The evaluation is two-step: first the keywords are looked for, and if there were any, the OpenAI model is called.
    Only messages that tested positive on both levels are classified as spam.
    """

    user = message.from_user

    if not hasattr(message, "text"):
        logger.warning("A message from user ID {n} (ID {i}) does not have text, cannot detect spam".format(i=user.id,
                                                                                                           n=user.full_name))
        return False

    layers = []
    confidence = 0

    if 'keywords' in settings.ANTISPAM_ENABLED and detect_keywords(message.text):
        confidence = 1
        layers.append('keywords')

    if 'emojis' in settings.ANTISPAM_ENABLED and detect_emojis(message):
        confidence = 1
        layers.append('emojis')

    if 'openai' in settings.ANTISPAM_ENABLED:
        confidence = detect_openai(message.text)
        if confidence > settings.ANTISPAM_OPENAI_CONFIDENCE_THRESHOLD:
            layers.append('openai')

    if len(layers) == 0:
        return False

    logger.info(
        "SPAM in a message from user ID {n} (ID {i}).  Layer(s): {l}.  Confidence: {c}.".format(c=confidence, i=user.id,
                                                                                                l=", ".join(layers),
                                                                                                n=user.full_name))

    db.spam_insert(message.text, user.id, ", ".join(layers), confidence)

    return True


async def detect_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect spam and take appropriate action"""

    if update.effective_message is None:
        logger.warning("The update does not have any message, cannot detect spam")
        return
    message = update.effective_message
    user = message.from_user

    if message.chat_id != settings.MAIN_CHAT_ID:
        # The message does not belong to the main chat, will not detect spam.
        return

    if db.is_good_member(user.id):
        # The message comes from a known user, will not detect spam.
        return

    try:
        if not is_spam(message):
            logger.info("The first message from user {full_name} (ID {id}) looks good".format(full_name=user.full_name,
                                                                                              id=user.id))
            db.register_good_member(user.id)
            return
    except Exception as e:
        logger.error("Exception while trying to detect spam:", exc_info=e)

        await context.bot.send_message(chat_id=settings.DEVELOPER_CHAT_ID,
                                       text=f"Exception caught while analysing spam: {str(e)}")
        return

    await safe_delete_message(context, message.id, message.chat.id)

    if settings.BOT_IS_MALE:
        delete_notice = i18n.default().gettext("ANTISPAM_MESSAGE_MC_SPAM_DETECTED_M {username}")
    else:
        delete_notice = i18n.default().gettext("ANTISPAM_MESSAGE_MC_SPAM_DETECTED_F {username}")

    posted_message = await context.bot.send_message(settings.MAIN_CHAT_ID,
                                                    delete_notice.format(username=message.from_user.full_name),
                                                    disable_notification=True)
    context.job_queue.run_once(delete_message, 15, data=(posted_message, False))


async def handle_query_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> [None, int]:
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return

    await query.answer()

    trans = i18n.trans(user)

    if query.data == ADMIN_DOWNLOAD_SPAM:
        spam = [record for record in db.spam_select_all()]
        await user.send_document(json.dumps(spam, ensure_ascii=False, indent=2).encode("utf-8"), filename="spam.json",
                                 reply_markup=None)
    elif query.data == ADMIN_DOWNLOAD_KEYWORDS:
        await user.send_document(get_keywords(), filename=KEYWORDS_FILENAME, reply_markup=None)
    elif query.data == ADMIN_UPLOAD_KEYWORDS:
        await query.message.reply_text(trans.gettext("ANTISPAM_MESSAGE_DM_ADMIN_REQUEST_KEYWORDS"))

        return ADMIN_UPLOADING_KEYWORDS
    elif query.data == ADMIN_UPLOAD_OPENAI:
        await query.message.reply_text(trans.gettext("ANTISPAM_MESSAGE_DM_ADMIN_REQUEST_OPENAI"))

        return ADMIN_UPLOADING_OPENAI


# noinspection PyUnusedLocal
async def handle_received_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trans = i18n.trans(update.effective_user)

    if await save_file_with_backup(update, KEYWORDS_FILE_PATH, "text/plain"):
        global keywords

        keywords = None

        await update.effective_message.reply_text(trans.gettext("ANTISPAM_MESSAGE_DM_ADMIN_KEYWORDS_UPDATED"),
                                                  reply_markup=None)

    return ConversationHandler.END


# noinspection PyUnusedLocal
async def handle_received_openai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_admin(user):
        logging.error("User {username} is not listed as administrator!".format(username=user.username))
        return ConversationHandler.END

    document = update.message.effective_attachment

    openai_file = await document.get_file()
    data = io.BytesIO()
    await openai_file.download_to_memory(data)

    trans = i18n.trans(user)

    if save_new_openai(data):
        await update.effective_message.reply_text(trans.gettext("ANTISPAM_MESSAGE_DM_ADMIN_OPENAI_UPDATED"),
                                                  reply_markup=None)
    else:
        await update.effective_message.reply_text(trans.gettext("ANTISPAM_MESSAGE_DM_ADMIN_OPENAI_CANNOT_USE"),
                                                  reply_markup=get_main_keyboard())

    return ConversationHandler.END


def init(application: Application, group):
    """Prepare the feature as defined in the configuration"""

    if not settings.ANTISPAM_ENABLED:
        return

    trans = i18n.default()

    # Register admin handlers
    if 'keywords' in settings.ANTISPAM_ENABLED:
        application.add_handler(
            ConversationHandler(entry_points=[CallbackQueryHandler(handle_query_admin, pattern=ADMIN_UPLOAD_KEYWORDS)],
                                states={ADMIN_UPLOADING_KEYWORDS: [
                                    MessageHandler(filters.ATTACHMENT, handle_received_keywords)]}, fallbacks=[]))

        application.add_handler(CallbackQueryHandler(handle_query_admin, pattern=ADMIN_DOWNLOAD_KEYWORDS))

        register_buttons(((InlineKeyboardButton(trans.gettext("ANTISPAM_BUTTON_DOWNLOAD_ANTISPAM_KEYWORDS"),
                                                callback_data=ADMIN_DOWNLOAD_KEYWORDS),
                           InlineKeyboardButton(trans.gettext("ANTISPAM_BUTTON_UPLOAD_ANTISPAM_KEYWORDS"),
                                                callback_data=ADMIN_UPLOAD_KEYWORDS)),))

    if 'openai' in settings.ANTISPAM_ENABLED:
        application.add_handler(
            ConversationHandler(entry_points=[CallbackQueryHandler(handle_query_admin, pattern=ADMIN_UPLOAD_OPENAI)],
                                states={ADMIN_UPLOADING_OPENAI: [
                                    MessageHandler(filters.ATTACHMENT, handle_received_openai)]}, fallbacks=[]))

        application.add_handler(CallbackQueryHandler(handle_query_admin, pattern=ADMIN_DOWNLOAD_SPAM))

        register_buttons(((InlineKeyboardButton(trans.gettext("ANTISPAM_BUTTON_DOWNLOAD_SPAM"),
                                                callback_data=ADMIN_DOWNLOAD_SPAM),
                           InlineKeyboardButton(trans.gettext("ANTISPAM_BUTTON_UPLOAD_ANTISPAM_OPENAI"),
                                                callback_data=ADMIN_UPLOAD_OPENAI)),))

    application.add_handler(MessageHandler(filters.TEXT & (~ filters.COMMAND), detect_spam), group=group)


def post_init(application: Application, group):
    """Post-init"""

    if not settings.ANTISPAM_ENABLED:
        return

    pass
