"""Runs the real converter child; no provider/browser/media devices."""
import hashlib
import pytest
from app.modules.studio.jobs import converted_pages

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
