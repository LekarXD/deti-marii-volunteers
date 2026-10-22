"""Runs the real converter child; no provider/browser/media devices."""
import asyncio
import hashlib
import os
import pytest
from app.modules.studio.jobs import converted_pages
from app.modules.studio.slides_convert import ConvertError
from app.modules.studio.tests.office_conversion_smoke import data as pptx

@pytest.mark.asyncio
async def test_real_pdf_pages_through_isolated_child(tmp_path):
    import fitz
    from PIL import Image
    import io
    document=fitz.open()
    for label in ('First slide','Second slide'):
        page=document.new_page(width=320,height=180);page.insert_text((20,40),label)
    pages=await converted_pages(document.tobytes(),tmp_path)
    assert len(pages)==2 and hashlib.sha256(pages[0]).digest()!=hashlib.sha256(pages[1]).digest()
    for data in pages:
        with Image.open(io.BytesIO(data)) as image:assert image.width>image.height and image.format=='JPEG'

@pytest.mark.asyncio
async def test_orphaned_libreoffice_child_is_killed_after_converter_exits(tmp_path,monkeypatch):
    # The real soffice wrapper exits while soffice.bin lives on in the converter's process group.
    pidfile=tmp_path/'orphan.pid';stub=tmp_path/'soffice';work=tmp_path/'work';work.mkdir()
    stub.write_text(f'#!/bin/sh\nsleep 300 &\necho $! > {pidfile}\nexit 1\n');stub.chmod(0o755)
    monkeypatch.setenv('OPORA_STUDIO_SOFFICE',str(stub))
    with pytest.raises(ConvertError,match='convert_failed'):await converted_pages(pptx(),work)
    pid=int(pidfile.read_text())
    for _ in range(50):
        try:os.kill(pid,0)
        except ProcessLookupError:break
        await asyncio.sleep(.1)
    else:
        os.kill(pid,9);pytest.fail('LibreOffice child outlived the converter')
