import joblib
import numpy as np
from openai import OpenAI
import logging

def get_text_predict_spam(text, api_key, threshold=0.5):

    with open("./nlp_experiments/bad_keywords.txt") as f:
        bad_keywords = []
        for line in f.readlines():
            #             print(line.strip())
            bad_keywords.append(line.strip())

    text_processed = text.lower()
    if any([bad_kw in text_processed for bad_kw in bad_keywords]):
        return 1
    else:

        # embedding
        client = OpenAI(
            api_key=api_key,
        )

        response = client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        embedding = response.data[0].embedding

        # Load the model using joblib
        filename = "./nlp_experiments/svm_model.joblib"
        model = joblib.load(filename)

        # Ensure the embedding is reshaped or adjusted as necessary based on how the model was trained
        embedding = np.array(embedding).reshape(1, -1)  # Reshape for a single sample prediction
        # Predict using the SVM model
        prediction = model.predict_proba(embedding)

        pred_conf = prediction[0][1]

        logging.warning(f"Spam confidence : {pred_conf} ")

        return int(pred_conf > threshold)  # Return the predicted label