
import faiss
import numpy as np
import json
import os

from embeddings import generate_embeddings


class VectorStore:

    def __init__(self):
        self.index = None
        self.documents = []

    # --------------------------------------------------
    # GENERATE NORMALIZED EMBEDDINGS
    # --------------------------------------------------

    def create_embeddings(self, texts):

        embeddings = generate_embeddings(texts)

        embeddings = np.asarray(
            embeddings,
            dtype="float32"
        )

        if embeddings.ndim != 2:
            raise ValueError(
                "Embeddings must be a 2D array."
            )

        if embeddings.shape[0] != len(texts):
            raise ValueError(
                "Embedding count does not match document count."
            )

        if embeddings.shape[1] == 0:
            raise ValueError(
                "Embedding dimension cannot be zero."
            )

        if not np.isfinite(embeddings).all():
            raise ValueError(
                "Embeddings contain invalid numerical values."
            )

        # Normalize vectors so inner product represents cosine similarity.
        faiss.normalize_L2(embeddings)

        return embeddings

    # --------------------------------------------------
    # BUILD OR UPDATE INDEX
    # --------------------------------------------------

    def build_index(self, chunks):

        if not chunks:
            raise ValueError(
                "No document chunks provided."
            )

        for chunk in chunks:

            if not isinstance(chunk, dict):
                raise ValueError(
                    "Invalid document chunk."
                )

            if not isinstance(chunk.get("text"), str):
                raise ValueError(
                    "Document chunk must contain text."
                )

            if not chunk["text"].strip():
                raise ValueError(
                    "Document chunk cannot be empty."
                )

        new_sources = {
            chunk.get("source")
            for chunk in chunks
            if chunk.get("source")
        }

        # Preserve previously indexed sources.
        existing_documents = [
            document
            for document in self.documents
            if document.get("source") not in new_sources
        ]

        combined_documents = (
            existing_documents + chunks
        )

        texts = [
            document["text"]
            for document in combined_documents
        ]

        embeddings = self.create_embeddings(texts)

        dimension = embeddings.shape[1]

        new_index = faiss.IndexFlatIP(dimension)

        new_index.add(embeddings)

        # Replace the active index only after successful construction.
        self.index = new_index
        self.documents = combined_documents

        unique_sources = {
            document.get("source")
            for document in self.documents
            if document.get("source")
        }

        print("FAISS index rebuilt successfully!")
        print("Total document chunks:", self.index.ntotal)
        print("Unique source files:", len(unique_sources))
        print("Embedding dimension:", dimension)

    # --------------------------------------------------
    # SEARCH
    # --------------------------------------------------

    def search(self, query, top_k=3):

        if self.index is None:
            raise ValueError(
                "Vector index is not initialized."
            )

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "Search query cannot be empty."
            )

        if top_k < 1:
            raise ValueError(
                "top_k must be at least 1."
            )

        query_embedding = self.create_embeddings(
            [query]
        )

        if query_embedding.shape[1] != self.index.d:
            raise ValueError(
                "Query embedding dimension does not match FAISS index."
            )

        k = min(top_k, self.index.ntotal)

        if k == 0:
            return []

        scores, indices = self.index.search(
            query_embedding,
            k
        )

        results = []

        for score, index in zip(
            scores[0],
            indices[0]
        ):

            if index == -1:
                continue

            result = self.documents[index].copy()

            result["similarity"] = float(score)

            results.append(result)

        return results

    # --------------------------------------------------
    # SAVE INDEX
    # --------------------------------------------------

    def save(self, folder="vector_data"):

        if self.index is None:
            raise ValueError(
                "No index to save."
            )

        os.makedirs(
            folder,
            exist_ok=True
        )

        index_path = os.path.join(
            folder,
            "index.faiss"
        )

        documents_path = os.path.join(
            folder,
            "documents.json"
        )

        faiss.write_index(
            self.index,
            index_path
        )

        with open(
            documents_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                self.documents,
                file,
                ensure_ascii=False,
                indent=2
            )

        print("FAISS index and metadata saved.")

    # --------------------------------------------------
    # LOAD INDEX
    # --------------------------------------------------

    def load(self, folder="vector_data"):

        index_path = os.path.join(
            folder,
            "index.faiss"
        )

        documents_path = os.path.join(
            folder,
            "documents.json"
        )

        if not os.path.exists(index_path):
            raise FileNotFoundError(
                "FAISS index file not found."
            )

        if not os.path.exists(documents_path):
            raise FileNotFoundError(
                "Document metadata file not found."
            )

        loaded_index = faiss.read_index(
            index_path
        )

        with open(
            documents_path,
            "r",
            encoding="utf-8"
        ) as file:

            loaded_documents = json.load(file)

        if loaded_index.ntotal != len(loaded_documents):
            raise ValueError(
                "FAISS index and document metadata are inconsistent."
            )

        if not isinstance(loaded_documents, list):
            raise ValueError(
                "Invalid document metadata."
            )

        self.index = loaded_index
        self.documents = loaded_documents

        print("FAISS index loaded successfully!")
        print("Total document chunks:", self.index.ntotal)
        print("Embedding dimension:", self.index.d)
