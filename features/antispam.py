"""
Antispam
"""

import io
import logging
import pathlib
import string

import joblib
import numpy as np
import telegram
from openai import OpenAI

from common import db
from settings import (ANTISPAM_ENABLED, ANTISPAM_EMOJIS_MAX_CUSTOM_EMOJI_COUNT, ANTISPAM_OPENAI_API_KEY,
                      ANTISPAM_OPENAI_CONFIDENCE_THRESHOLD)

KEYWORDS_FILE_PATH = pathlib.Path(__file__).parent / "resources" / "bad_keywords.txt"
OPENAI_FILE_PATH = pathlib.Path(__file__).parent / "resources" / "svm_model.joblib"

keywords = None
openai_model = None

logger = logging.getLogger(__name__)


def detect_keywords(text: str) -> bool:
    """Detect spam using keywords"""

    global keywords

    if keywords is None:
        logger.info("Loading the list of stop words")
        keywords = []
        with open(KEYWORDS_FILE_PATH) as f:
            for line in f.readlines():
                keywords.append(line.strip())

    text_processed = [word.strip(string.punctuation) for word in text.lower().split()]

    result = any([bad_kw in text_processed for bad_kw in keywords])
    logger.info("Stop words found: {result}".format(result=result))

    return result


def get_keywords() -> io.BytesIO:
    """Return contents of the actual keywords file"""

    with open(KEYWORDS_FILE_PATH, "rb") as inp:
        data = io.BytesIO(inp.read())
        return data


def save_new_keywords(data: io.BytesIO) -> bool:
    """Reset the keywords file with new contents.  The new list will be used on the next call to `detect_keywords()`."""

    data.seek(0)
    with open(KEYWORDS_FILE_PATH, "wb") as out_file:
        out_file.write(data.read())

    global keywords

    keywords = None

    return True


def detect_emojis(message: telegram.Message) -> bool:
    """Detect spam that uses custom emojis"""

    if not hasattr(message, "entities"):
        return False

    custom_emoji_count = 0
    for e in message.entities:
        if e.type == telegram.MessageEntity.CUSTOM_EMOJI:
            custom_emoji_count += 1
            if custom_emoji_count > ANTISPAM_EMOJIS_MAX_CUSTOM_EMOJI_COUNT:
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
    client = OpenAI(api_key=ANTISPAM_OPENAI_API_KEY)

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
        logger.warning("A message from user ID {n} (ID {i}) does not have text, cannot detect spam".format(
            i=user.id, n=user.full_name))
        return False

    layers = []
    confidence = 0

    if 'keywords' in ANTISPAM_ENABLED and detect_keywords(message.text):
        confidence = 1
        layers.append('keywords')

    if 'emojis' in ANTISPAM_ENABLED and detect_emojis(message):
        confidence = 1
        layers.append('emojis')

    if 'openai' in ANTISPAM_ENABLED:
        confidence = detect_openai(message.text)
        if confidence > ANTISPAM_OPENAI_CONFIDENCE_THRESHOLD:
            layers.append('openai')

    if len(layers) == 0:
        return False

    logger.info("SPAM in a message from user ID {n} (ID {i}).  Layer(s): {l}.  Confidence: {c}.".format(
        c=confidence, i=user.id, l=", ".join(layers), n=user.full_name))

    db.spam_insert(message.text, user.id, ", ".join(layers), confidence)

    return True
