
from document_processor import clean_text, create_chunks

sample_text = """
Equity investments represent ownership in companies.
Debt investments generally provide fixed income.
Gold can provide portfolio diversification.
"""

cleaned = clean_text(sample_text)

chunks = create_chunks(
    cleaned,
    chunk_size=10,
    overlap=2
)

print("Cleaned text:")
print(cleaned)

print("\nGenerated chunks:")

for index, chunk in enumerate(chunks, start=1):
    print(f"Chunk {index}: {chunk}")

print("\nTotal chunks:", len(chunks))
