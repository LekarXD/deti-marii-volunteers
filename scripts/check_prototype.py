"""Check artboard links, markup, logic syntax and state-dependent template lookups."""
from pathlib import Path
from html.parser import HTMLParser
import json, re, subprocess
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'prototype'
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Parser(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.errors=[]
 def handle_starttag(self,t,a):
  if t not in VOID:self.stack.append(t)
 def handle_startendtag(self,t,a):pass
 def handle_endtag(self,t):
  if not self.stack or self.stack[-1]!=t:self.errors.append((self.getpos()[0],t,self.stack[-3:]));return
  self.stack.pop()
files=list(P.glob('*.dc.html'))
for p in files:
 t=p.read_text();v=Parser();v.feed(t)
 assert not v.errors and not v.stack,(p.name,v.errors,v.stack)
 for link in re.findall(r'href="([^"#?]+\.dc\.html)"',t):assert (P/link).exists(),(p.name,link)
 for hole in re.findall(r'\{\{(.*?)\}\}',t):assert re.fullmatch(r'[\w$.]+',hole.strip()),(p.name,hole)
 logic=re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>',t,re.S).group(1)
 result=subprocess.run(['node','-e','new Function(process.argv[1]);',logic],capture_output=True,text=True)
 assert result.returncode==0,(p.name,result.stderr)
c=json.loads((P/'canvas.json').read_text());assert set(c['boards'])==set(p.name for p in files)
print('PASS:',len(files),'artboards: balanced tags, links, holes, JS syntax, canvas membership.')

# Working additions must not fall back to OS selects or date/time popups.
new_names=[p.stem.replace('.body','') for p in (ROOT/'prototype-src').glob('*.body.html')]+['Reflection']
for name in new_names:
 text=(P/(name+'.dc.html')).read_text()
 assert not re.search(r'<select\b|<input\b[^>]*type="(?:date|time|month|datetime-local)"',text),(name,'native control')
 assert not re.search(r'\{\{uiDate\.[dwm]\.',text),(name,'loop scope in calendar')
print('PASS: all additions use styled selection and calendar controls.')
