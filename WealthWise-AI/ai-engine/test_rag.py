
from vector_store import VectorStore
from rag import generate_answer


# Load previously created FAISS index
store = VectorStore()

store.load("vector_data")


# Ask a financial question
question = "What investments represent ownership in companies?"


# Generate grounded answer
result = generate_answer(
    question,
    store,
    top_k=3
)


print("\nWEALTHWISE AI ANSWER")
print("--------------------")

print(result["answer"])


print("\nSOURCE REFERENCES")
print("--------------------")

for source in result["sources"]:

    print(
        f"File: {source['file']} | "
        f"Page: {source['page']} | "
        f"Similarity: {source['similarity']}"
    )
