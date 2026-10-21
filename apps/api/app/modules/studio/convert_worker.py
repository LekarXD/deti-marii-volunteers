"""Isolated, killable media process. No DB session, provider key or API settings import."""
import argparse,json,subprocess
from pathlib import Path
from .slides_convert import sniff,normalize_image,strip_external_links,soffice_command,converted_pdf,pdf_page_count,render_pdf_page,ConvertError,MAX_PAGES

def convert(source:Path,output:Path):
    data=source.read_bytes()
    if len(data)>50*1024*1024:raise ConvertError('source_size_limit')
    kind=sniff(data);pages=[]
    if kind=='image':pages=[normalize_image(data)]
    elif kind in ('pdf','pptx'):
        document=output/('source.'+kind);document.write_bytes(strip_external_links(data) if kind=='pptx' else data)
        pdf=document
        if kind=='pptx':
            argv,env=soffice_command(document,output)
            process=subprocess.run(argv,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180,check=False)
            if process.returncode:raise ConvertError('convert_failed')
            pdf=converted_pdf(document,output)
        count=pdf_page_count(pdf)
        if not 1<=count<=MAX_PAGES:raise ConvertError('page_limit')
        total=0
        for index in range(count):
            page=render_pdf_page(pdf,index);total+=len(page)
            if total>64*1024*1024:raise ConvertError('render_size_limit')
            pages.append(page)
    else:raise ConvertError('unsupported_type')
    for index,page in enumerate(pages):(output/f'page-{index}.jpg').write_bytes(page)
    return {'state':'ready','pages':len(pages)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);args=parser.parse_args();output=Path(args.output)
    try:result=convert(Path(args.input),output)
    except ConvertError as exc:result={'state':'failed','error_code':exc.code}
    except ImportError:result={'state':'failed','error_code':'converter_unavailable'}
    except subprocess.TimeoutExpired:result={'state':'failed','error_code':'conversion_timeout'}
    except Exception:result={'state':'failed','error_code':'convert_failed'}
    (output/'manifest.json').write_text(json.dumps(result))

if __name__=='__main__':main()
