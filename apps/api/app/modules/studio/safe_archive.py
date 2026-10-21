"""Bounded ZIP/OOXML reads — decompression-bomb (zip-bomb) guards.

DOCX/XLSX/PPTX are ZIP containers. ``ZipFile.read(name)`` and python-docx's
``Document(...)`` decompress a member fully into RAM with no bound, so a small
uploaded file (a few MB compressed) can declare — or actually expand to — many
GB uncompressed and OOM the worker (DEFLATE tops out ~1000:1).

Two layers, both used by the docx ingest paths:

* :func:`assert_zip_within_limits` — cheap fast-reject from the central
  directory (declared sizes + entry count), before any decompression.
* :func:`safe_read_zip_member` — bounded *actual* decompression: reads at most
  ``max_bytes + 1`` uncompressed bytes so a lying/undersized header can't slip a
  bomb past the declared-size check.

``utils/`` may import stdlib only (layer rules); ``zipfile``/``io`` qualify.
"""

from __future__ import annotations

import io
import zipfile
import zlib

# Generous ceilings — far above any legitimate homework/material docx. A real
# document.xml is a few MB; embedded media a few MB each. Pathological inputs
# are refused, normal ones are unaffected.
MAX_ENTRIES = 4096
MAX_MEMBER_UNCOMPRESSED = 100 * 1024 * 1024  # 100 MB per member
MAX_TOTAL_UNCOMPRESSED = 400 * 1024 * 1024  # 400 MB across all members


class ZipBombError(ValueError):
    """Raised when a ZIP declares or expands beyond the configured limits."""


def assert_zip_within_limits(
    zf: zipfile.ZipFile,
    *,
    max_entries: int = MAX_ENTRIES,
    max_member_uncompressed: int = MAX_MEMBER_UNCOMPRESSED,
    max_total_uncompressed: int = MAX_TOTAL_UNCOMPRESSED,
) -> None:
    """Fast-reject a ZIP whose central directory declares a bomb.

    Uses ``ZipInfo.file_size`` (the declared uncompressed size — no
    decompression), so it's cheap. It catches honestly-declared bombs; a
    lying-small header is caught later by :func:`safe_read_zip_member`.

    Raises:
        ZipBombError: entry count or declared uncompressed size over limit.
    """
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise ZipBombError(f"zip has {len(infos)} entries > {max_entries} cap")
    total = 0
    for info in infos:
        if info.file_size > max_member_uncompressed:
            raise ZipBombError(f"zip member {info.filename!r} declares {info.file_size} bytes uncompressed")
        total += info.file_size
        if total > max_total_uncompressed:
            raise ZipBombError(f"zip declares > {max_total_uncompressed} bytes uncompressed total")


def safe_read_zip_member(zf: zipfile.ZipFile, name: str, *, max_bytes: int = MAX_MEMBER_UNCOMPRESSED) -> bytes:
    """Decompress ``name`` with a hard cap on uncompressed bytes.

    ``ZipExtFile.read(n)`` decompresses incrementally, so reading ``max_bytes+1``
    never materialises more than that in RAM even if the member lies about its
    size.

    Raises:
        ZipBombError: the member expands past ``max_bytes``.
        KeyError: ``name`` is not in the archive (propagated from ``zf.open``).
    """
    with zf.open(name) as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ZipBombError(f"zip member {name!r} expands past {max_bytes} bytes (decompression bomb)")
    return data


def docx_bytes_within_limits(file_bytes: bytes) -> bool:
    """Validate every package part before handing immutable bytes to python-docx.

    python-docx eagerly reads ALL relationship-linked parts, including binary
    media. Check declared limits before decompression, then bounded-read every
    member and verify its size/CRC. Duplicate names are rejected so validation
    and the parser cannot resolve a part differently. The caller must parse
    these same bytes, never reopen an independently mutable file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            assert_zip_within_limits(
                zf,
                max_entries=MAX_ENTRIES,
                max_member_uncompressed=MAX_MEMBER_UNCOMPRESSED,
                max_total_uncompressed=MAX_TOTAL_UNCOMPRESSED,
            )
            members = zf.infolist()
            if len({info.filename for info in members}) != len(members):
                return False
            total = 0
            for info in members:
                data = safe_read_zip_member(
                    zf,
                    info.filename,
                    max_bytes=min(MAX_MEMBER_UNCOMPRESSED, MAX_TOTAL_UNCOMPRESSED - total),
                )
                if len(data) != info.file_size:
                    return False
                total += len(data)
        return True
    except (ZipBombError, zipfile.BadZipFile, OSError, KeyError, RuntimeError, NotImplementedError, zlib.error):
        return False


__all__ = [
    "ZipBombError",
    "assert_zip_within_limits",
    "safe_read_zip_member",
    "docx_bytes_within_limits",
    "MAX_ENTRIES",
    "MAX_MEMBER_UNCOMPRESSED",
    "MAX_TOTAL_UNCOMPRESSED",
]
