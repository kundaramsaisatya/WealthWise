"""Independent validation and bounded persistence for uploaded statements."""
from pathlib import Path
import zipfile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_XLSX_ENTRIES = 2000
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 100


class UploadTooLargeError(ValueError):
    pass


async def save_upload_limited(upload, destination: Path, max_bytes: int = MAX_UPLOAD_BYTES):
    """Stream an UploadFile to disk without ever writing beyond max_bytes."""
    total = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLargeError("File exceeds the 10 MB upload limit.")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if total == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("Uploaded file is empty.")
    return total


def validate_uploaded_file(file_path: Path, extension: str):
    """Validate actual file structure, not only the user-supplied extension."""
    with file_path.open("rb") as source:
        signature = source.read(8)

    if extension == ".pdf":
        if len(signature) < 5 or signature[:5] != b"%PDF-":
            raise ValueError("File content does not match a PDF document.")
        return

    if extension != ".xlsx":
        raise ValueError("Only PDF and XLSX files are accepted.")

    if signature[:4] != b"PK\x03\x04":
        raise ValueError("File content does not match an XLSX document.")

    try:
        with zipfile.ZipFile(file_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_XLSX_ENTRIES:
                raise ValueError("XLSX contains too many archive entries.")

            names = set()
            uncompressed_total = 0
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ValueError("XLSX contains an unsafe archive path.")
                if entry.flag_bits & 0x1:
                    raise ValueError("Encrypted XLSX files are not supported.")

                names.add(name)
                uncompressed_total += entry.file_size
                if uncompressed_total > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ValueError("XLSX expands beyond the allowed size.")

                if entry.file_size > 0:
                    if entry.compress_size == 0:
                        raise ValueError("XLSX contains an invalid compressed entry.")
                    if entry.file_size / entry.compress_size > MAX_XLSX_COMPRESSION_RATIO:
                        raise ValueError("XLSX compression ratio exceeds the safety limit.")

            if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
                raise ValueError("ZIP archive is not a valid XLSX workbook.")
    except zipfile.BadZipFile as error:
        raise ValueError("XLSX archive is corrupt.") from error
