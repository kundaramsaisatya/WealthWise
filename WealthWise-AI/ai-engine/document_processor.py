
from pypdf import PdfReader


def extract_text_from_pdf(file_path):

    reader = PdfReader(file_path)

    extracted_pages = []

    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text()

        if text and text.strip():

            extracted_pages.append({
                "page": page_number,
                "text": text
            })

    return extracted_pages


def clean_text(text):

    return " ".join(text.split())


def create_chunks(text, chunk_size=500, overlap=100):

    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Overlap must be smaller than chunk size")

    words = text.split()

    chunks = []

    step = chunk_size - overlap

    for start in range(0, len(words), step):

        chunk_words = words[start:start + chunk_size]

        if not chunk_words:
            break

        chunks.append(" ".join(chunk_words))

    return chunks


def process_pdf(file_path, document_id, original_filename):

    pages = extract_text_from_pdf(file_path)

    all_chunks = []

    for page_data in pages:

        cleaned_text = clean_text(page_data["text"])

        chunks = create_chunks(cleaned_text)

        for chunk_number, chunk in enumerate(chunks, start=1):

            all_chunks.append({
                "document_id": str(document_id),
                "text": chunk,
                "page": page_data["page"],
                "chunk": chunk_number,
                "source": original_filename,
                "document_type": "pdf"
            })

    return all_chunks