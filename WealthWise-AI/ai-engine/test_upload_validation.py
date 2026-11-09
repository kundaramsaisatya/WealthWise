import tempfile
import unittest
import zipfile
from pathlib import Path

from upload_validation import (
    MAX_UPLOAD_BYTES, UploadTooLargeError, save_upload_limited,
    validate_uploaded_file,
)


class FakeUpload:
    def __init__(self, data, chunk_size=65536):
        self.data, self.offset, self.chunk_size = data, 0, chunk_size

    async def read(self, size=-1):
        if self.offset >= len(self.data):
            return b""
        end = min(self.offset + min(size, self.chunk_size), len(self.data))
        chunk = self.data[self.offset:end]
        self.offset = end
        return chunk


class UploadValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_file_within_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "upload.pdf"
            payload = b"%PDF-" + b"x" * 100
            self.assertEqual(await save_upload_limited(FakeUpload(payload), path), len(payload))
            self.assertEqual(path.read_bytes(), payload)

    async def test_rejects_oversized_upload_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.pdf"
            with self.assertRaises(UploadTooLargeError):
                await save_upload_limited(FakeUpload(b"x" * (MAX_UPLOAD_BYTES + 1)), path)
            self.assertFalse(path.exists())

    async def test_rejects_empty_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.pdf"
            with self.assertRaisesRegex(ValueError, "empty"):
                await save_upload_limited(FakeUpload(b""), path)
            self.assertFalse(path.exists())

    def test_accepts_pdf_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.pdf"
            path.write_bytes(b"%PDF-1.7 content")
            validate_uploaded_file(path, ".pdf")

    def test_rejects_renamed_non_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.pdf"
            path.write_bytes(b"not a pdf")
            with self.assertRaisesRegex(ValueError, "PDF"):
                validate_uploaded_file(path, ".pdf")

    def test_accepts_minimal_xlsx_package(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.xlsx"
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("xl/workbook.xml", "<workbook/>")
            validate_uploaded_file(path, ".xlsx")

    def test_rejects_arbitrary_zip_as_xlsx(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("notes.txt", "hello")
            with self.assertRaisesRegex(ValueError, "valid XLSX"):
                validate_uploaded_file(path, ".xlsx")

    def test_rejects_corrupt_xlsx(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.xlsx"
            path.write_bytes(b"PK\x03\x04not-a-zip")
            with self.assertRaises(ValueError):
                validate_uploaded_file(path, ".xlsx")


if __name__ == "__main__":
    unittest.main()
