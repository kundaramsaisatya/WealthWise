
import faiss
import numpy as np
import json
import os

from embeddings import generate_embeddings


class VectorStore:

    def __init__(self):

        self.index = None
        self.documents = []

    def build_index(self, chunks):

        texts = [chunk["text"] for chunk in chunks]

        embeddings = generate_embeddings(texts)

        embeddings = np.asarray(
            embeddings,
            dtype="float32"
        )

        dimension = embeddings.shape[1]

        self.index = faiss.IndexFlatIP(dimension)

        self.index.add(embeddings)

        self.documents = chunks

        print("FAISS index created!")
        print("Total vectors:", self.index.ntotal)

    def search(self, query, top_k=3):

        if self.index is None:
            raise ValueError("Vector index is not initialized")

        query_embedding = generate_embeddings([query])

        query_embedding = np.asarray(
            query_embedding,
            dtype="float32"
        )

        k = min(top_k, self.index.ntotal)

        if k == 0:
            return []

        scores, indices = self.index.search(
            query_embedding,
            k
        )

        results = []

        for score, index in zip(scores[0], indices[0]):

            if index == -1:
                continue

            result = self.documents[index].copy()

            result["similarity"] = float(score)

            results.append(result)

        return results

    def save(self, folder="vector_data"):

        if self.index is None:
            raise ValueError("No index to save")

        os.makedirs(folder, exist_ok=True)

        faiss.write_index(
            self.index,
            os.path.join(folder, "index.faiss")
        )

        with open(
            os.path.join(folder, "documents.json"),
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                self.documents,
                file,
                ensure_ascii=False,
                indent=2
            )

    def load(self, folder="vector_data"):

        self.index = faiss.read_index(
            os.path.join(folder, "index.faiss")
        )

        with open(
            os.path.join(folder, "documents.json"),
            "r",
            encoding="utf-8"
        ) as file:

            self.documents = json.load(file)
