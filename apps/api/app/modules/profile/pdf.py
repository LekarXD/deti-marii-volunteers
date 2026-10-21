"""Local, Cyrillic PDF renderer; no remote fonts, fake signatures or seals."""
import io
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
from app.core.pdf_font import font_path

def render_document(snapshot):
    if 'OporaPDF' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('OporaPDF',str(font_path())))
        pdfmetrics.registerFont(TTFont('OporaPDFBold',str(Path(__file__).parent/'pdf_assets'/'DejaVuSans-Bold.ttf')))
    output=io.BytesIO();width,height=A4
    styles={
        'brand':ParagraphStyle('brand',fontName='OporaPDFBold',fontSize=14,leading=19,textColor=colors.HexColor('#242424')),
        'title':ParagraphStyle('title',fontName='OporaPDFBold',fontSize=30,leading=38,spaceAfter=22),
        'body':ParagraphStyle('body',fontName='OporaPDF',fontSize=11,leading=18,spaceAfter=12),
        'small':ParagraphStyle('small',fontName='OporaPDF',fontSize=9,leading=14,textColor=colors.HexColor('#646464')),
        'total':ParagraphStyle('total',fontName='OporaPDFBold',fontSize=20,leading=28),
    }
    def paragraph(text,kind='body'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[kind])
    story=[paragraph('опора','brand'),Spacer(1,14),paragraph(snapshot['foundation_name'],'small'),Spacer(1,38),paragraph('Справка о волонтёрской помощи' if snapshot['kind']=='certificate' else 'Благодарственное письмо','title'),paragraph(snapshot['display_name'],'brand'),Spacer(1,20),paragraph('Для: '+snapshot['recipient']),paragraph('Период: '+snapshot['period_from']+' — '+snapshot['period_to'])]
    total=snapshot['total_minutes'];hours,minutes=divmod(total,60)
    total_box=Table([[paragraph(f'{total} минут','total')],[paragraph(f'{hours} ч {minutes:02d} мин подтверждённой помощи')]],colWidths=[width-112])
    total_box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#FFEB7A')),('LEFTPADDING',(0,0),(-1,-1),18),('RIGHTPADDING',(0,0),(-1,-1),18),('TOPPADDING',(0,0),(-1,0),16),('BOTTOMPADDING',(0,-1),(-1,-1),8)]))
    story.extend([Spacer(1,8),total_box,Spacer(1,26)])
    if snapshot.get('body'):story.append(paragraph(snapshot['body']))
    else:story.append(paragraph('Минуты учтены по подтверждённым фактам посещения и решениям координаторов. Запросы, ожидающие проверки, в справку не включены.'))
    story.extend([Spacer(1,26),paragraph('Документ № '+snapshot['document_id'],'small'),paragraph('Сформирован: '+snapshot['issued_at'],'small'),paragraph('Электронная выписка из журнала волонтёрской помощи. Подпись и печать в этот файл не добавлены.','small')])
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#deded8'));canvas.line(56,46,width-56,46)
        canvas.setFont('OporaPDF',8);canvas.setFillColor(colors.HexColor('#646464'));canvas.drawString(56,30,'Опора · '+str(doc.page))
    SimpleDocTemplate(output,pagesize=A4,rightMargin=56,leftMargin=56,topMargin=45,bottomMargin=65,title='Волонтёрская помощь',author=snapshot['foundation_name']).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
