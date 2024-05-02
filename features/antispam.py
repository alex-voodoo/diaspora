import logging
import string

import joblib
import numpy as np
from openai import OpenAI

stop_words = None
openai_model = None

logger = logging.getLogger(__name__)

def detect_stop_words(text):
    global stop_words

    if stop_words is None:
        logger.info("Loading the list of stop words")
        stop_words = []
        with open("features/resources/bad_keywords.txt") as f:
            for line in f.readlines():
                stop_words.append(line.strip())

    text_processed = [word.strip(string.punctuation) for word in text.lower().split()]

    result = any([bad_kw in text_processed for bad_kw in stop_words])
    logger.info("Stop words found: {result}".format(result=result))

    return result


def detect_openai(text, api_key, threshold=0.5):
    global openai_model

    # Load the model using joblib
    if openai_model is None:
        logger.info("Loading the OpenAI model")
        filename = "features/resources/svm_model.joblib"
        openai_model = joblib.load(filename)

    # embedding
    client = OpenAI(api_key=api_key)

    response = client.embeddings.create(input=text, model="text-embedding-3-small")
    embedding = response.data[0].embedding

    # Ensure the embedding is reshaped or adjusted as necessary based on how the model was trained
    embedding = np.array(embedding).reshape(1, -1)  # Reshape for a single sample prediction
    # Predict using the SVM model
    prediction = openai_model.predict_proba(embedding)

    pred_conf = prediction[0][1]

    logger.info("Spam confidence: {confidence} and threshold: {threshold}".format(
        confidence=pred_conf, threshold=threshold))

    return pred_conf > threshold  # Return the predicted label
