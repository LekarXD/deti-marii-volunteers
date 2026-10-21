"""Shared bounded validation for PDF and Office document uploads.

Both the assignment-editor attachment endpoint (``routers/web_media.upload_file``,
curator surface, public ``task-media`` bucket) and the LMS lesson-material
endpoint (``routers/lms/manage_materials``, instructor surface, private
``materials`` bucket) accept the same three document formats. Keeping the size
cap, the allowed/ambiguous declared MIME sets, and the magic-byte sniff in ONE
place stops the two endpoints from drifting apart ("this DOCX worked in the
assignment editor but not in the Конструктор").

The OOXML checks are also reused by the canonical file-signature and macro-scan
gates. This module imports only stdlib and a sibling ``utils`` primitive.
"""

from __future__ import annotations

import io
import stat
import zipfile
from xml.etree import ElementTree

from .safe_archive import ZipBombError, assert_zip_within_limits, safe_read_zip_member

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

MAX_SAFE_ZIP_ENTRIES = 4_096
MAX_SAFE_ZIP_MEMBER_BYTES = 100 * 1024 * 1024
MAX_SAFE_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_SAFE_ZIP_COMPRESSION_RATIO = 200
_MAX_OOXML_XML_BYTES = 32 * 1024 * 1024
_MAX_ZIP_DIRECTORY_BYTES = 8 * 1024 * 1024
_ZIP_MAGIC = b"PK\x03\x04"
_ZIP_EOCD_MAGIC = b"PK\x05\x06"
_OOXML_MAIN_PARTS = {
    "word/document.xml": (DOCX_MIME, "document"),
    "xl/workbook.xml": (XLSX_MIME, "workbook"),
    "ppt/presentation.xml": (PPTX_MIME, "presentation"),
}
_ZIP_ERRORS = (
    ElementTree.ParseError,
    KeyError,
    NotImplementedError,
    OSError,
    RuntimeError,
    ZipBombError,
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
)

# Files (PDF/DOCX/DOC/PPTX) can legitimately be larger than images — a long
# reading list, rubric document, or lecture deck easily passes 10 MB. 25 MB
# bounds Storage growth and request bodies without rejecting real materials.
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024

# Lecture decks are the one document class that routinely blows past that cap:
# a slide deck of scans/photos is 30-50 MB where a homework attachment is a
# couple of MB. Раньше преподаватель упирался в 25 МБ, оставлял пустой
# файл-блок — и урок переставал сохраняться целиком (инцидент 25.08.2026).
# A separate ceiling keeps the numerous curator attachments bounded while the
# far rarer lesson material gets the room it needs. Still well under the edge
# cap (Caddyfile.web-edge: 96 MB on /api/*) and the size-aware upload timeout.
MAX_LESSON_MATERIAL_BYTES = 50 * 1024 * 1024

# Canonical Office/PDF types. The declared multipart ``Content-Type`` is only a
# cheap first gate; the authoritative check is :func:`detect_document_mime`.
ALLOWED_DOCUMENT_MIME = frozenset(
    {
        "application/pdf",
        DOCX_MIME,
        PPTX_MIME,
        "application/msword",
    }
)

# Browsers routinely send a generic/zip MIME for DOCX/DOC instead of the
# canonical Office type (DOCX is a ZIP container). These declared types pass the
# cheap early gate and are validated for real by the magic-byte sniff, which the
# client cannot spoof.
AMBIGUOUS_DOCUMENT_MIME = frozenset(
    {
        "",
        "application/octet-stream",
        "application/zip",
        "application/x-zip-compressed",
    }
)

# Canonical MIME → file extension for building the storage key.
DOCUMENT_MIME_TO_EXT = {
    "application/pdf": "pdf",
    DOCX_MIME: "docx",
    PPTX_MIME: "pptx",
    "application/msword": "doc",
}


def _safe_member_name(name: str) -> bool:
    if not name or len(name) > 1_024 or "\x00" in name or "\\" in name or name.startswith("/"):
        return False
    parts = name.rstrip("/").split("/")
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts) and ":" not in parts[0]


def _zip_directory_is_bounded(file_bytes: bytes) -> bool:
    """Reject oversized classic central directories before ``ZipFile`` allocates."""
    tail = file_bytes[-65_557:]
    offset = tail.rfind(_ZIP_EOCD_MAGIC)
    while offset >= 0:
        if len(tail) - offset >= 22:
            comment_size = int.from_bytes(tail[offset + 20 : offset + 22], "little")
            if offset + 22 + comment_size == len(tail):
                break
        offset = tail.rfind(_ZIP_EOCD_MAGIC, 0, offset)
    if offset < 0:
        return False
    disk = int.from_bytes(tail[offset + 4 : offset + 6], "little")
    directory_disk = int.from_bytes(tail[offset + 6 : offset + 8], "little")
    disk_entries = int.from_bytes(tail[offset + 8 : offset + 10], "little")
    entries = int.from_bytes(tail[offset + 10 : offset + 12], "little")
    directory_size = int.from_bytes(tail[offset + 12 : offset + 16], "little")
    return (
        disk == directory_disk == 0
        and disk_entries == entries
        and entries != 0xFFFF
        and entries <= MAX_SAFE_ZIP_ENTRIES
        and directory_size <= _MAX_ZIP_DIRECTORY_BYTES
    )


def _validated_zip(file_bytes: bytes) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]] | None:
    """Open a ZIP only when its metadata is safe for downstream parsers."""
    if not file_bytes.startswith(_ZIP_MAGIC) or not _zip_directory_is_bounded(file_bytes):
        return None
    archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    try:
        assert_zip_within_limits(
            archive,
            max_entries=MAX_SAFE_ZIP_ENTRIES,
            max_member_uncompressed=MAX_SAFE_ZIP_MEMBER_BYTES,
            max_total_uncompressed=MAX_SAFE_ZIP_UNCOMPRESSED_BYTES,
        )
        members: dict[str, zipfile.ZipInfo] = {}
        total_size = 0
        total_compressed = 0
        for info in archive.infolist():
            name = info.filename
            unix_mode = info.external_attr >> 16
            unsafe = (
                not _safe_member_name(name)
                or name in members
                or bool(info.flag_bits & 0x1)
                or stat.S_ISLNK(unix_mode)
                or bool(info.file_size and not info.compress_size)
                or bool(info.compress_size and info.file_size / info.compress_size > MAX_SAFE_ZIP_COMPRESSION_RATIO)
            )
            if unsafe:
                archive.close()
                return None
            members[name] = info
            if not info.is_dir():
                total_size += info.file_size
                total_compressed += info.compress_size
        if total_compressed and total_size / total_compressed > MAX_SAFE_ZIP_COMPRESSION_RATIO:
            archive.close()
            return None
        return archive, members
    except _ZIP_ERRORS:
        archive.close()
        raise


def zip_archive_is_safe(file_bytes: bytes) -> bool:
    """Return whether bytes form a ZIP within entry, size and ratio limits."""
    archive = None
    try:
        validated = _validated_zip(bytes(file_bytes))
        if validated is None:
            return False
        archive, _members = validated
        return True
    except _ZIP_ERRORS:
        return False
    finally:
        if archive is not None:
            archive.close()


def _ooxml_root_matches(archive: zipfile.ZipFile, info: zipfile.ZipInfo, expected_root: str) -> bool:
    if info.file_size > _MAX_OOXML_XML_BYTES:
        return False
    data = safe_read_zip_member(archive, info.filename, max_bytes=_MAX_OOXML_XML_BYTES)
    if len(data) != info.file_size:
        return False
    root = ElementTree.fromstring(data)
    return root.tag.rsplit("}", 1)[-1] == expected_root


def detect_ooxml_mime(file_bytes: bytes) -> str | None:
    """Classify a bounded OOXML package; reject arbitrary or corrupt ZIPs."""
    archive = None
    try:
        validated = _validated_zip(bytes(file_bytes))
        if validated is None:
            return None
        archive, members = validated
        manifest = members.get("[Content_Types].xml")
        if manifest is None or not _ooxml_root_matches(archive, manifest, "Types"):
            return None
        matches = [(part, contract) for part, contract in _OOXML_MAIN_PARTS.items() if part in members]
        if len(matches) != 1:
            return None
        main_part, (mime, expected_root) = matches[0]
        return mime if _ooxml_root_matches(archive, members[main_part], expected_root) else None
    except _ZIP_ERRORS:
        return None
    finally:
        if archive is not None:
            archive.close()


def detect_document_mime(buf: bytes) -> str | None:
    """Return the canonical MIME for a document by magic bytes; ``None`` if unknown.

    ``Content-Type`` from the multipart boundary is client-controlled and cannot
    be trusted alone — an upload labelled ``application/pdf`` that actually
    contains HTML would otherwise be served back via a Storage URL on our domain,
    useful for phishing. Sniffing the leading bytes is the gate the client
    cannot spoof.

    Modern Office formats (DOCX/PPTX) are ZIP archives sharing the
    ``PK\\x03\\x04`` magic. :func:`detect_ooxml_mime` validates the bounded
    container and requires its OOXML manifest plus exact main part, so an
    arbitrary or corrupt ZIP is not promoted to a document.
    Legacy ``.doc``/``.ppt`` share the OLE2 magic and can't be distinguished by
    header — we map that to ``.doc`` (the supported legacy format).
    """
    if len(buf) < 8:
        return None
    if buf[:5] == b"%PDF-":
        return "application/pdf"
    if buf[:4] == b"PK\x03\x04":
        detected = detect_ooxml_mime(buf)
        return detected if detected in {DOCX_MIME, PPTX_MIME} else None
    if buf[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "application/msword"
    return None
