"""
Antispam
"""

import io
import logging
import pathlib
import string

import joblib
import numpy as np
from openai import OpenAI

from common import db
from settings import ANTISPAM_ENABLED, ANTISPAM_OPENAI_API_KEY, ANTISPAM_OPENAI_CONFIDENCE_THRESHOLD

KEYWORDS_FILE_PATH = pathlib.Path(__file__).parent / "resources" / "bad_keywords.txt"
OPENAI_FILE_PATH = pathlib.Path(__file__).parent / "resources" / "svm_model.joblib"

keywords = None
openai_model = None

logger = logging.getLogger(__name__)


def detect_keywords(text) -> bool:
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
    with open(KEYWORDS_FILE_PATH, "wb") as outp:
        outp.write(data.read())

    global keywords

    keywords = None

    return True


def detect_openai(text) -> float:
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
    try:
        new_model = joblib.load(data)
    except Exception:
        return False

    global openai_model

    openai_model = new_model

    data.seek(0)
    with open(OPENAI_FILE_PATH, "wb") as outp:
        outp.write(data.read())

    return True


def is_spam(text, tg_id) -> bool:
    """Evaluates `text` and returns whether it looks like spam

    The evaluation is two-step: first the keywords are looked for, and if there were any, the OpenAI model is called.
    Only messages that tested positive on both levels are classified as spam.
    """

    layers = []
    confidence = 0

    if 'keywords' in ANTISPAM_ENABLED:
        if not detect_keywords(text):
            return False
        confidence = 1
        layers.append('keywords')

    if 'openai' in ANTISPAM_ENABLED:
        confidence = detect_openai(text)
        if confidence < ANTISPAM_OPENAI_CONFIDENCE_THRESHOLD:
            return False
        layers.append('openai')

    logger.info("Spam confidence: {confidence}".format(confidence=confidence))

    db.spam_insert(text, tg_id, ", ".join(layers), confidence)

    return True
