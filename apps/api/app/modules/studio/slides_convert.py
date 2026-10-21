"""Presentation file → slide pictures (worker side, plus the upload sniff).

* the type is decided by the bytes, never by the name: PDF, PowerPoint
  (pptx / legacy ppt), OpenDocument (odp), Keynote (key), or pictures;
* office formats go through LibreOffice headless into PDF, then every PDF
  page becomes one JPEG (PyMuPDF), long side ≤ 1920 px;
* LibreOffice runs with a throw-away profile, macros off, a dead HTTP proxy
  and no environment secrets; PowerPoint packages lose their external
  relationships (linked pictures/OLE on someone else's server) before they
  reach it — a deck must not make the worker fetch URLs.

Everything here is synchronous and CPU/IO bound: callers run it in a thread
or (LibreOffice) as a subprocess.
"""

import io
import os
import re
import shutil
import zipfile
from pathlib import Path

from .document_upload import PPTX_MIME, detect_ooxml_mime, zip_archive_is_safe

MAX_PAGES = 100
SLIDE_LONG_SIDE = 1920
JPEG_QUALITY = 86
MAX_IMAGE_PIXELS = 60_000_000
OFFICE_KINDS = frozenset({"pptx", "ppt", "odp", "key"})
EXTENSIONS = {"pdf": "pdf", "pptx": "pptx", "ppt": "ppt", "odp": "odp", "key": "key"}
_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ODP_MIME = b"application/vnd.oasis.opendocument.presentation"
_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


class ConvertError(RuntimeError):
    """A safe, user-explainable failure code (``detail`` may carry a page count)."""

    def __init__(self, code: str, detail: int | None = None) -> None:
        self.code, self.detail = code, detail
        super().__init__(code)


# ── what did we get ─────────────────────────────────────────────────────────────


def image_ext(data: bytes) -> str | None:
    head = bytes(data[:16])
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def _zip_kind(data: bytes) -> str | None:
    if detect_ooxml_mime(data) == PPTX_MIME:
        return "pptx"
    if not zip_archive_is_safe(data):
        return None
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        mimetype = archive.getinfo("mimetype") if "mimetype" in names else None
        if mimetype and mimetype.file_size <= 200 and archive.read("mimetype").strip() == _ODP_MIME:
            return "odp"
        if "Index/Document.iwa" in names or "index.apxl" in names or "index.apxl.gz" in names:
            return "key"
    return None


def _ole_kind(data: bytes) -> str | None:
    import olefile

    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except (OSError, ValueError):
        return None
    try:
        return "ppt" if ole.exists("PowerPoint Document") else None
    finally:
        ole.close()


def sniff(data: bytes) -> str | None:
    """``pdf`` | ``pptx`` | ``ppt`` | ``odp`` | ``key`` | ``image`` | ``None``."""
    if len(data) < 16:
        return None
    if data[:5] == b"%PDF-":
        return "pdf"
    if image_ext(data):
        return "image"
    if data[:4] == b"PK\x03\x04":
        return _zip_kind(data)
    if data[:8] == _OLE2:
        return _ole_kind(data)
    return None


# ── LibreOffice ──────────────────────────────────────────────────────────────────


def strip_external_links(data: bytes) -> bytes:
    """Drop OOXML relationships that point outside the package (except hyperlinks).

    LibreOffice would otherwise try to load a linked picture/OLE object from
    an arbitrary URL — including the internal network — while rendering.
    """
    pattern = re.compile(
        rb"<(?:\w+:)?Relationship\b[^>]*\bTargetMode\s*=\s*[\"']External[\"'][^>]*?(?:/>|>\s*</(?:\w+:)?Relationship>)"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename.endswith(".rels"):
                body = pattern.sub(lambda m: m.group(0) if _HYPERLINK.encode() in m.group(0) else b"", body)
            dst.writestr(info, body)
    return out.getvalue()


_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetProxyType" oor:op="fuse"><value>2</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPProxyName" oor:op="fuse"><value>127.0.0.1</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPProxyPort" oor:op="fuse"><value>9</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPSProxyName" oor:op="fuse"><value>127.0.0.1</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetHTTPSProxyPort" oor:op="fuse"><value>9</value></prop></item>
<item oor:path="/org.openoffice.Inet/Settings"><prop oor:name="ooInetNoProxy" oor:op="fuse"><value></value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
</oor:items>
"""


def soffice_binary() -> str | None:
    return os.environ.get("OPORA_STUDIO_SOFFICE") or shutil.which("soffice") or shutil.which("libreoffice")


def soffice_command(src: Path, workdir: Path) -> tuple[list[str], dict[str, str]]:
    """Argv and a minimal environment for one isolated PDF export."""
    binary = soffice_binary()
    if not binary:
        raise ConvertError("converter_missing")
    profile = workdir / "profile"
    (profile / "user").mkdir(parents=True, exist_ok=True)
    (profile / "user" / "registrymodifications.xcu").write_text(_PROFILE, encoding="utf-8")
    out = workdir / "out"
    out.mkdir(exist_ok=True)
    argv = [
        binary,
        "--headless",
        "--invisible",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--norestore",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out),
        str(src),
    ]
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(workdir),
        "LANG": "C.UTF-8",
        "SAL_USE_VCLPLUGIN": "svp",
        "TMPDIR": str(workdir),
    }
    return argv, env


def converted_pdf(src: Path, workdir: Path) -> Path:
    pdf = workdir / "out" / (src.stem + ".pdf")
    if not pdf.is_file() or pdf.stat().st_size < 64:
        raise ConvertError("convert_failed")
    return pdf


# ── pages ───────────────────────────────────────────────────────────────────────


def _jpeg(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=False)
    return buffer.getvalue()


def pdf_page_count(path: Path) -> int:
    import fitz

    try:
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise ConvertError("pdf_locked")
            return doc.page_count
    except ConvertError:
        raise  # a ConvertError is a RuntimeError too: «pdf_locked» must reach the teacher as is
    except (RuntimeError, ValueError) as exc:  # fitz.FileDataError is a RuntimeError
        raise ConvertError("convert_failed") from exc


def render_pdf_page(path: Path, index: int) -> bytes:
    """One page as JPEG, long side ≤ 1920 px, never upscaled more than 3×."""
    import fitz
    from PIL import Image

    try:
        with fitz.open(path) as doc:
            page = doc[index]
            rect = page.rect
            zoom = min(3.0, SLIDE_LONG_SIDE / max(rect.width, rect.height, 1))
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except (RuntimeError, ValueError, IndexError) as exc:
        raise ConvertError("convert_failed") from exc
    return _jpeg(image)


def normalize_image(data: bytes) -> bytes:
    """Upright RGB JPEG, long side ≤ 1920 px; first frame of an animation."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ConvertError("image_too_large")
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                flat = Image.new("RGB", image.size, (255, 255, 255))
                flat.paste(image, mask=image.getchannel("A"))
                image = flat
            else:
                image = image.convert("RGB")
            image.thumbnail((SLIDE_LONG_SIDE, SLIDE_LONG_SIDE), Image.Resampling.LANCZOS)
            return _jpeg(image)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ConvertError("image_failed") from exc
