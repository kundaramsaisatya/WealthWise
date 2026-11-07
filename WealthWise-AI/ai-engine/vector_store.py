
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
            raise ValueError("No document chunks provided.")

        for chunk in chunks:

            if not isinstance(chunk, dict):
                raise ValueError("Invalid document chunk.")

            if not chunk.get("document_id"):
                raise ValueError(
                    "Every chunk must have a document_id."
                )

            if not isinstance(chunk.get("text"), str):
                raise ValueError(
                    "Document chunk must contain text."
                )

            if not chunk["text"].strip():
                raise ValueError(
                    "Document chunk cannot be empty."
                )

        # Identify documents being added or replaced
        new_document_ids = {
            str(chunk["document_id"])
            for chunk in chunks
        }

        # Preserve chunks belonging to other documents
        existing_documents = [
            document
            for document in self.documents
            if str(document.get("document_id"))
            not in new_document_ids
        ]

        combined_documents = existing_documents + chunks

        # Generate embeddings for all remaining chunks
        texts = [
            document["text"]
            for document in combined_documents
        ]

        embeddings = self.create_embeddings(texts)

        # Create a new FAISS index
        dimension = embeddings.shape[1]

        new_index = faiss.IndexFlatIP(dimension)

        new_index.add(embeddings)

        # Update the vector store only after successful indexing
        self.index = new_index
        self.documents = combined_documents

        print("FAISS index built successfully!")
        print("Total chunks:", self.index.ntotal)
        print("Embedding dimension:", self.index.d)

        if not chunks:
            raise ValueError("No document chunks provided.")

        for chunk in chunks:

            if not isinstance(chunk, dict):
                raise ValueError("Invalid document chunk.")

            if not chunk.get("document_id"):
                raise ValueError(
                    "Every chunk must have a document_id."
                )

            if not isinstance(chunk.get("text"), str):
                raise ValueError(
                    "Document chunk must contain text."
                )

            if not chunk["text"].strip():
                raise ValueError(
                    "Document chunk cannot be empty."
                )

    #Delete
   
    def remove_document(self, document_id):
        document_id = str(document_id)

        remaining_documents = [
            document
            for document in self.documents
            if str(document.get("document_id")) != document_id
        ]

        removed_count = len(self.documents) - len(remaining_documents)

        if removed_count == 0:
            return 0

        if remaining_documents:
            texts = [
                document["text"]
                for document in remaining_documents
            ]

            embeddings = self.create_embeddings(texts)

            new_index = faiss.IndexFlatIP(embeddings.shape[1])
            new_index.add(embeddings)

            self.index = new_index

        else:
            self.index = None

        self.documents = remaining_documents

        print(f"Removed {removed_count} chunks for document {document_id}")

        return removed_count

    # --------------------------------------------------
    # SAVE FAISS INDEX
    # --------------------------------------------------

    def save(self, folder_path):

        if self.index is None:
            raise ValueError("Cannot save an empty FAISS index.")

        os.makedirs(folder_path, exist_ok=True)

        index_path = os.path.join(folder_path, "index.faiss")
        documents_path = os.path.join(folder_path, "documents.json")

        faiss.write_index(self.index, index_path)

        with open(documents_path, "w", encoding="utf-8") as file:
            json.dump(self.documents, file, ensure_ascii=False, indent=2)

        print("FAISS index and documents saved successfully.")

    # --------------------------------------------------
    # LOAD FAISS INDEX
    # --------------------------------------------------

    def load(self, folder_path):

        index_path = os.path.join(folder_path, "index.faiss")
        documents_path = os.path.join(folder_path, "documents.json")

        if not os.path.exists(index_path):
            raise FileNotFoundError("FAISS index file not found.")

        if not os.path.exists(documents_path):
            raise FileNotFoundError("Documents metadata file not found.")

        loaded_index = faiss.read_index(index_path)

        with open(documents_path, "r", encoding="utf-8") as file:
            loaded_documents = json.load(file)

        if loaded_index.ntotal != len(loaded_documents):
            raise ValueError(
                "FAISS index and document metadata are inconsistent."
            )

        self.index = loaded_index
        self.documents = loaded_documents

        print("FAISS index loaded successfully!")
        print("Total document chunks:", self.index.ntotal)
        print("Embedding dimension:", self.index.d)

    def search(self, query, top_k=3, document_type=None):

        if not isinstance(query, str) or not query.strip():
            return []

        if self.index is None or not self.documents:
            return []

        if not isinstance(top_k, int) or top_k <= 0:
            return []

        # Generate embedding for the user's question.
        query_embedding = self.create_embeddings([query])

        # When a document type is requested, search the full index and
        # filter by metadata before selecting top results. Searching only
        # the global top_k first could return unrelated Excel chunks and
        # hide relevant PDF pages.
        if document_type:
            results_count = self.index.ntotal
        else:
            results_count = min(top_k, self.index.ntotal)

        scores, indices = self.index.search(
            query_embedding,
            results_count
        )

        results = []

        for score, index_position in zip(scores[0], indices[0]):

            if index_position < 0:
                continue

            document = self.documents[index_position].copy()

            if document_type and (
                str(document.get("document_type", "")).lower()
                != document_type.lower()
            ):
                continue

            document["similarity"] = float(score)
            results.append(document)

            if len(results) >= top_k:
                break

        return results