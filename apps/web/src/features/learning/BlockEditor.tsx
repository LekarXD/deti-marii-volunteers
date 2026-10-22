import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {Button,Combobox,Field,Icon,Input,Textarea,cx,type IconName} from '../../ui';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {appPath} from '../../basePath';

export type EditableBlock=Record<string,unknown> & {type:string};
export type EditableQuestion={q:string;o:string[];a:number;e:string};
export const blankQuestion=():EditableQuestion=>({q:'',o:['',''],a:0,e:''});
type Scenario=components['schemas']['SimulatorScenarioPublicView'];

/** The six blocks of the «Добавить блок» menu: label and art colour. */
export const blockKinds:[string,string,string][]=[['text','Текст','art-b'],['video','Видео','art-o'],['image','Картинка','art-g'],['file','Файл','art-g'],['quiz','Вопрос','art-y'],['sim','Тренажёр','art-v']];
// Blocks of the imported introduction keep their own forms.
const legacyLabels:Record<string,string>={lead:'Вводный абзац',task:'Задание',callout:'Важно',rules:'Правила',icards:'Карточки',facts:'Цифры',timeline:'История',story:'История участника',phrases:'Как говорить'};
export const blockLabel=(type:string)=>blockKinds.find(([kind])=>kind===type)?.[1]??legacyLabels[type]??'Блок';
const blockArt=(type:string)=>blockKinds.find(([kind])=>kind===type)?.[2]??'art-b';
const icons:Record<string,IconName>={video:'video',image:'image',file:'file',quiz:'checklist',sim:'message'};
export function BlockIcon({type}:{type:string}){return icons[type]?<Icon name={icons[type]}/>:<svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>;}
export const newBlock=(type:string):EditableBlock=>type==='quiz'?{type,items:[blankQuestion()]}:type==='video'?{type,url:''}:type==='file'?{type,title:''}:type==='text'?{type,text:''}:{type};

const str=(value:unknown)=>typeof value==='string'?value:'';
const providers:[RegExp,string][]=[[/^(www\.|m\.)?(youtube\.com|youtube-nocookie\.com|youtu\.be)$/,'YouTube'],[/^(www\.)?rutube\.ru$/,'Rutube'],[/^(www\.|m\.)?(vk\.com|vk\.ru|vkvideo\.ru)$/,'VK Видео']];
/** A quick preview check; the server decides and builds the embed. */
export function videoProvider(url:string){try{const host=new URL(/^[a-z]+:\/\//i.test(url.trim())?url.trim():`https://${url.trim()}`).hostname.toLowerCase();return providers.find(([pattern])=>pattern.test(host))?.[1]??null;}catch{return null;}}
function fileSize(bytes:unknown){if(typeof bytes!=='number'||!bytes)return '';return bytes<1024*1024?`${Math.max(1,Math.round(bytes/1024))} КБ`:`${(bytes/1024/1024).toFixed(1).replace('.',',')} МБ`;}
async function uploadAsset(file:File){
 const buffer=await file.arrayBuffer(),digest=await crypto.subtle.digest('SHA-256',buffer);
 const checksum=Array.from(new Uint8Array(digest)).map(x=>x.toString(16).padStart(2,'0')).join('');
 const intent=await api<{id:string;upload_url:string}>('/assets/upload-intents',{method:'POST',body:{content_type:file.type,expected_size:file.size,checksum}});
 for(let offset=0;offset<file.size;offset+=1024*1024)await api(intent.upload_url,{method:'PATCH',headers:{'X-Upload-Offset':String(offset)},body:buffer.slice(offset,offset+1024*1024)});
 await api(`/assets/${intent.id}/complete-upload`,{method:'POST'});
 return intent.id;
}
function Drop({text,accept,onUploaded}:{text:string;accept:string;onUploaded:(assetId:string,file:File)=>void}){
 const input=useRef<HTMLInputElement>(null),[over,setOver]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState('');
 async function take(file?:File){if(!file||pending)return;setPending(true);setError('');try{onUploaded(await uploadAsset(file),file);}catch(e){setError(e instanceof Error?e.message:'Не удалось загрузить файл');}finally{setPending(false);}}
 return <div className={cx('upload-drop',over&&'is-over')} onDragOver={e=>{e.preventDefault();setOver(true);}} onDragLeave={()=>setOver(false)} onDrop={e=>{e.preventDefault();setOver(false);void take(e.dataTransfer.files[0]);}}>
  <input ref={input} type="file" tabIndex={-1} aria-hidden="true" accept={accept} className="sr-only" onChange={e=>{void take(e.target.files?.[0]);e.target.value='';}}/>
  <span className="p">{pending?'Загружаем и проверяем файл…':text}</span>
  <Button variant="secondary" size="sm" disabled={pending} onClick={()=>input.current?.click()}>Выбрать файл</Button>
  {error&&<p className="err" role="alert">{error}</p>}
 </div>;
}

function TextBody({block,id,update}:{block:EditableBlock;id:string;update:(delta:Record<string,unknown>)=>void}){
 const ref=useRef<HTMLTextAreaElement>(null),text=str(block.text);
 function apply(next:string,start:number,end:number){update({text:next});requestAnimationFrame(()=>{ref.current?.focus();ref.current?.setSelectionRange(start,end);});}
 function wrap(mark:string,fallback:string){const el=ref.current;const s=el?.selectionStart??text.length,e=el?.selectionEnd??text.length,picked=text.slice(s,e)||fallback;apply(text.slice(0,s)+mark+picked+mark+text.slice(e),s+mark.length,s+mark.length+picked.length);}
 function lines(prefix:string){const el=ref.current;const s=el?.selectionStart??text.length,e=el?.selectionEnd??s,from=text.lastIndexOf('\n',s-1)+1;const part=text.slice(from,e).split('\n').map(line=>line.startsWith(prefix)?line:prefix+line).join('\n');apply(text.slice(0,from)+part+text.slice(e),from,from+part.length);}
 function link(){const el=ref.current;const s=el?.selectionStart??text.length,e=el?.selectionEnd??s,label=text.slice(s,e)||'текст ссылки',piece=`[${label}](https://)`;apply(text.slice(0,s)+piece+text.slice(e),s+label.length+3,s+piece.length-1);}
 return <>
  <div className="rte-bar" role="toolbar" aria-label="Оформление текста"><button type="button" aria-label="Жирный" onClick={()=>wrap('**','жирный текст')}>Ж</button><button type="button" aria-label="Курсив" style={{fontStyle:'italic'}} onClick={()=>wrap('*','курсив')}>К</button><button type="button" aria-label="Заголовок" onClick={()=>lines('## ')}>H</button><button type="button" aria-label="Список" onClick={()=>lines('- ')}><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/></svg></button><button type="button" aria-label="Ссылка" onClick={link}><Icon name="link"/></button></div>
  <label className="sr-only" htmlFor={id}>Текст блока</label>
  <textarea ref={ref} id={id} className="textarea rte-text" value={text} onChange={e=>update({text:e.target.value})}/>
 </>;
}
function VideoBody({block,update}:{block:EditableBlock;update:(delta:Record<string,unknown>)=>void}){
 const url=str(block.url),provider=videoProvider(url),caption=str(block.title)||'Видео по ссылке';
 if(block.asset_id&&!url)return <div className="video-prev" role="img" aria-label={str(block.title)||'Запись урока'}><span className="play"><Icon name="play"/></span><span className="video-cap">{str(block.title)||'Запись урока'}</span></div>;
 return <><Field label="Ссылка на VK Видео, Rutube или YouTube" error={url.trim()&&!provider?'Вставьте ссылку на видео из VK Видео, Rutube или YouTube':undefined}><Input type="url" value={url} placeholder="https://vkvideo.ru/" onChange={e=>update({url:e.target.value})}/></Field>
  {url.trim()&&provider&&<a className="video-prev" href={/^[a-z]+:\/\//i.test(url.trim())?url.trim():`https://${url.trim()}`} target="_blank" rel="noreferrer" aria-label={`${caption}, открыть на ${provider}`}><span className="play"><Icon name="play"/></span><span className="video-cap">{caption}</span></a>}</>;
}
function ImageBody({block,lessonId,update}:{block:EditableBlock;lessonId:string;update:(delta:Record<string,unknown>)=>void}){
 const [local,setLocal]=useState<string|null>(null);
 useEffect(()=>()=>{if(local)URL.revokeObjectURL(local);},[local]);
 if(!block.asset_id)return <Drop text="Перетащите картинку сюда" accept="image/png,image/jpeg,image/webp" onUploaded={(asset_id,file)=>{setLocal(URL.createObjectURL(file));update({asset_id,title:str(block.title)||''});}}/>;
 return <><img className="block-image" src={local??appPath(`/api/v1/coord/learning/lessons/${lessonId}/assets/${String(block.asset_id)}`)} alt={str(block.title)||'Картинка к уроку'}/><Field label="Подпись"><Input value={str(block.title)} onChange={e=>update({title:e.target.value})}/></Field></>;
}
function FileBody({block,update}:{block:EditableBlock;update:(delta:Record<string,unknown>)=>void}){
 if(!block.asset_id)return <Drop text="Перетащите файл сюда" accept="application/pdf,image/png,image/jpeg,image/webp" onUploaded={(asset_id,file)=>update({asset_id,title:str(block.title)||file.name,size:file.size})}/>;
 return <div className="row file-row"><Icon name="file"/><span className="grow strong">{str(block.title)||'Материал'}</span><span className="meta">{fileSize(block.size)}</span></div>;
}
export function QuestionBody({question,index,many,onChange}:{question:EditableQuestion;index:number;many:boolean;onChange:(value:EditableQuestion)=>void}){
 const set=(delta:Partial<EditableQuestion>)=>onChange({...question,...delta});
 return <>
  <Field label={many?`Вопрос ${index+1}`:'Вопрос'}><Input value={question.q} onChange={e=>set({q:e.target.value})}/></Field>
  <div className="q-opts" role="radiogroup" aria-label="Верный ответ">{question.o.map((option,j)=><div key={j} className={cx('q-opt',question.a===j&&'right')}>
   <button type="button" className="q-mark" role="radio" aria-checked={question.a===j} aria-label={`Вариант ${j+1} верный`} onClick={()=>set({a:j})}>{question.a===j&&<Icon name="check"/>}</button>
   <input className="q-text" aria-label={`Вариант ответа ${j+1}`} placeholder="Вариант ответа" value={option} onChange={e=>set({o:question.o.map((x,k)=>k===j?e.target.value:x)})}/>
   {question.o.length>2&&<button type="button" className="iconbtn" aria-label={`Удалить вариант ${j+1}`} onClick={()=>set({o:question.o.filter((_,k)=>k!==j),a:question.a===j?0:question.a>j?question.a-1:question.a})}><Icon name="x"/></button>}
  </div>)}</div>
  {question.o.length<12&&<Button variant="ghost" size="sm" onClick={()=>set({o:[...question.o,'']})}><Icon name="plus"/>Вариант ответа</Button>}
  <Field label="Объяснение после ответа"><Textarea rows={2} value={question.e} onChange={e=>set({e:e.target.value})}/></Field>
 </>;
}
export function QuestionsEditor({questions,onChange}:{questions:EditableQuestion[];onChange:(value:EditableQuestion[])=>void}){
 return <>{questions.map((q,i)=><QuestionBody key={i} question={q} index={i} many={questions.length>1} onChange={value=>onChange(questions.map((x,j)=>j===i?value:x))}/>)}</>;
}
function SimBody({block,update}:{block:EditableBlock;update:(delta:Record<string,unknown>)=>void}){
 const scenarios=useQuery({queryKey:keys.list('learning-scenarios'),queryFn:({signal})=>api<{items:Scenario[]}>('/simulator/scenarios?limit=100',{signal}),retry:false});
 const items=scenarios.data?.items??[],id=str(block.scenario_id),title=str(block.title)||items.find(item=>item.id===id)?.title||'';
 return <>
  <Combobox label="Сценарий тренажёра" value={id} placeholder={scenarios.isPending?'Загружаем сценарии…':items.length?'Выберите сценарий':'Нет опубликованных сценариев'} disabled={!items.length} options={items.map(item=>({value:item.id,label:item.title}))} onChange={value=>update({scenario_id:value,title:items.find(item=>item.id===value)?.title??''})}/>
  {id&&<div className="row wrap" style={{justifyContent:'space-between'}}><span className="sc-quote">«{title}»</span><Link className="btn btn-ghost btn-sm" to={`/fund/scenarios?scenario=${encodeURIComponent(id)}`}>Открыть в тренажёре</Link></div>}
 </>;
}
const vectorFields:Record<string,string[]>={facts:['Число','Подпись'],timeline:['Год','Событие','Описание'],story:['Заголовок','Описание','Иконка'],phrases:['Так говорим','Так не говорим']};
function LegacyBody({block,update}:{block:EditableBlock;update:(delta:Record<string,unknown>)=>void}){
 const items=(Array.isArray(block.items)?block.items:[]) as unknown[];
 const updateItem=(i:number,value:unknown)=>update({items:items.map((x,j)=>i===j?value:x)});
 return <>
  {['lead','task','callout'].includes(block.type)&&<Field label={block.type==='task'?'Задание для волонтёра':'Текст'}><Textarea rows={4} value={str(block.text)} onChange={e=>update({text:e.target.value})}/></Field>}
  {block.type==='task'&&<label className="checkline"><input type="checkbox" checked={block.required===true} onChange={e=>update({required:e.target.checked})}/>Ответ обязателен для завершения урока</label>}
  {block.type==='callout'&&<Combobox label="Выделение" value={str(block.tone)||'info'} onChange={tone=>update({tone})} options={[{value:'info',label:'Информация'},{value:'warn',label:'Важно'}]}/>}
  {block.type==='story'&&<Field label="Вступление"><Textarea value={str(block.intro)} onChange={e=>update({intro:e.target.value})}/></Field>}
  {block.type==='rules'&&<>{items.map((item,i)=><Field key={i} label={`Правило ${i+1}`}><Input value={str(item)} onChange={e=>updateItem(i,e.target.value)}/></Field>)}<Button variant="ghost" size="sm" onClick={()=>update({items:[...items,'']})}><Icon name="plus"/>Правило</Button></>}
  {vectorFields[block.type]&&<>{items.map((row,i)=><div className="legacy-row" key={i}>{vectorFields[block.type].map((label,j)=><Field label={label} key={j}><Input value={str((row as string[])[j])} onChange={e=>{const next=[...(row as string[])];next[j]=e.target.value;updateItem(i,next);}}/></Field>)}<Button variant="ghost" size="sm" onClick={()=>update({items:items.filter((_,j)=>j!==i)})}>Удалить строку</Button></div>)}<Button variant="ghost" size="sm" onClick={()=>update({items:[...items,vectorFields[block.type].map(()=> '')]})}><Icon name="plus"/>Строка</Button></>}
  {block.type==='icards'&&<>{(items as Record<string,unknown>[]).map((item,i)=><div className="legacy-row" key={i}>{[['title','Заголовок'],['text','Текст']].map(([name,label])=><Field label={label} key={name}><Input value={str(item[name])} onChange={e=>updateItem(i,{...item,[name]:e.target.value})}/></Field>)}<Button variant="ghost" size="sm" onClick={()=>update({items:items.filter((_,j)=>j!==i)})}>Удалить карточку</Button></div>)}<Button variant="ghost" size="sm" onClick={()=>update({items:[...items,{title:'',text:'',icon:'heart'}]})}><Icon name="plus"/>Карточка</Button></>}
 </>;
}

/** One block card: type art and label, up/down/delete tools, then the block's own form. */
export function BlockCard({block,index,count,lessonId,onChange,onDelete,onMove}:{block:EditableBlock;index:number;count:number;lessonId:string;onChange:(value:EditableBlock)=>void;onDelete:()=>void;onMove:(direction:number)=>void}){
 const label=blockLabel(block.type),update=(delta:Record<string,unknown>)=>onChange({...block,...delta});
 const items=(Array.isArray(block.items)?block.items:[]) as EditableQuestion[];
 let body:ReactNode;
 switch(block.type){
  case 'text':body=<TextBody block={block} id={`block-${lessonId}-${index}`} update={update}/>;break;
  case 'video':body=<VideoBody block={block} update={update}/>;break;
  case 'image':body=<ImageBody block={block} lessonId={lessonId} update={update}/>;break;
  case 'file':body=<FileBody block={block} update={update}/>;break;
  case 'quiz':body=<QuestionsEditor questions={items} onChange={value=>update({items:value})}/>;break;
  case 'sim':body=<SimBody block={block} update={update}/>;break;
  default:body=<LegacyBody block={block} update={update}/>;
 }
 return <div className="block">
  <div className="block-head"><span className={`art ${blockArt(block.type)}`} aria-hidden="true"><BlockIcon type={block.type}/></span><span className="block-type">{label}</span>
   <span className="block-tools">
    <button type="button" className="iconbtn" aria-label={`Поднять блок «${label}»`} disabled={index===0} onClick={()=>onMove(-1)}><Icon name="chevron-down" style={{transform:'rotate(180deg)'}}/></button>
    <button type="button" className="iconbtn" aria-label={`Опустить блок «${label}»`} disabled={index===count-1} onClick={()=>onMove(1)}><Icon name="chevron-down"/></button>
    <button type="button" className="iconbtn" aria-label={`Удалить блок «${label}»`} onClick={onDelete}><Icon name="trash"/></button>
   </span>
  </div>
  <div className="block-body">{body}</div>
 </div>;
}
