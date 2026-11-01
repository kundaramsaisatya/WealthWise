
import numpy as np
from sentence_transformers import SentenceTransformer


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

EMBEDDING_DIMENSION = 384
BATCH_SIZE = 32

model = SentenceTransformer(MODEL_NAME)


# --------------------------------------------------
# GENERATE EMBEDDINGS
# --------------------------------------------------

def generate_embeddings(texts):

    if not isinstance(texts, (list, tuple)):
        raise ValueError(
            "Input must be a list of text strings."
        )

    if not texts:
        return np.empty(
            (0, EMBEDDING_DIMENSION),
            dtype="float32"
        )

    if any(
        not isinstance(text, str) or not text.strip()
        for text in texts
    ):
        raise ValueError(
            "All input texts must be non-empty strings."
        )

    embeddings = model.encode(
        list(texts),
        batch_size=BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    embeddings = np.asarray(
        embeddings,
        dtype="float32"
    )

    if embeddings.shape != (
        len(texts),
        EMBEDDING_DIMENSION
    ):
        raise ValueError(
            "Unexpected embedding dimensions: "
            f"{embeddings.shape}"
        )

    if not np.isfinite(embeddings).all():
        raise ValueError(
            "Generated embeddings contain invalid values."
        )

    return embeddings
