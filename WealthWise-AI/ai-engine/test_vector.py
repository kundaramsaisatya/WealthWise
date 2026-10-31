
from vector_store import VectorStore

documents = [
    {
        "text": "Equity investments represent ownership in companies.",
        "page": 1,
        "source": "portfolio.pdf"
    },
    {
        "text": "Debt investments generally provide fixed income.",
        "page": 2,
        "source": "portfolio.pdf"
    },
    {
        "text": "Gold can provide diversification to a portfolio.",
        "page": 3,
        "source": "portfolio.pdf"
    },
    {
        "text": "The investor holds shares in technology companies.",
        "page": 4,
        "source": "portfolio.pdf"
    }
]

store = VectorStore()

store.build_index(documents)

query = "What investments represent company ownership?"

results = store.search(query, top_k=3)

print("\nSearch Results:")

for result in results:

    print("\nText:", result["text"])
    print("Page:", result["page"])
    print("Similarity:", round(result["similarity"], 4))

store.save()
