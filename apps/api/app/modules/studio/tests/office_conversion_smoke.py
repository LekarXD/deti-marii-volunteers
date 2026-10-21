"""Opt-in real LibreOffice smoke using a generated inert local PPTX; no external input.
Run in the dedicated media environment with native headless LibreOffice available.
"""
import io,zipfile,asyncio,tempfile
from pathlib import Path
from app.modules.studio.jobs import converted_pages
ns='http://schemas.openxmlformats.org/'
files={
'[Content_Types].xml':f'<Types xmlns="{ns}package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>',
'_rels/.rels':f'<Relationships xmlns="{ns}package/2006/relationships"><Relationship Id="rId1" Type="{ns}officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
'ppt/presentation.xml':f'<p:presentation xmlns:p="{ns}presentationml/2006/main" xmlns:a="{ns}drawingml/2006/main" xmlns:r="{ns}officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>',
'ppt/_rels/presentation.xml.rels':f'<Relationships xmlns="{ns}package/2006/relationships"><Relationship Id="rId1" Type="{ns}officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>',
'ppt/slides/slide1.xml':f'<p:sld xmlns:p="{ns}presentationml/2006/main" xmlns:a="{ns}drawingml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/><p:sp><p:nvSpPr><p:cNvPr id="2" name="Fixture title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="914400"/><a:ext cx="9144000" cy="914400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="3200"/><a:t>Real PPTX fixture</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'}
def data():
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w') as archive:
  for name,value in files.items():archive.writestr(name,value)
 return output.getvalue()
async def run():
 with tempfile.TemporaryDirectory(prefix='opora-pptx-') as directory:
  pages=await converted_pages(data(),Path(directory));print({'actual_pptx_pages':len(pages),'bytes':sum(map(len,pages))})
if __name__=='__main__':asyncio.run(run())
