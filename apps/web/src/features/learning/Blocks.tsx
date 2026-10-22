import {appPath} from '../../basePath';
import {useRef,useState,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {AlertCircle, BookOpen, Calendar, CheckCircle, Clock, Eye, Hand, Heart, Home, MapPin, MessageCircle, Music, Palette, Phone, Shield, Smile, Sparkles, Star, Users} from 'lucide-react';
import {Button,Field,Textarea} from '../../ui';
import {api} from '../../api/transport';

const icons = {palette: Palette, book:BookOpen, users:Users, heart:Heart, home:Home, hand:Hand, shield:Shield, smile:Smile, star:Star, calendar:Calendar, pin:MapPin, message:MessageCircle, music:Music, sparkle:Sparkles, eye:Eye, clock:Clock, phone:Phone, alert:AlertCircle, 'check-circle':CheckCircle};
type Item = {q:string;o:string[];icon?:string;title?:string;text?:string};
export type Block = {id:string;required?:boolean;asset_id?:string;type:string;text?:string;title?:string;intro?:string;duration?:string;src?:string;tone?:string;items?:unknown[];embed_url?:string;scenario_id?:string};
/** Only the embed addresses the server builds from VK Video, Rutube and YouTube links. */
export const isVideoEmbed=(url?:string)=>!!url&&/^https:\/\/(www\.youtube-nocookie\.com\/embed\/|rutube\.ru\/play\/embed\/|vkvideo\.ru\/video_ext\.php\?)/.test(url);
function inline(text:string){
 const parts:ReactNode[]=[],pattern=/\*\*([^*]+)\*\*|\*([^*]+)\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;let last=0,match:RegExpExecArray|null;
 while((match=pattern.exec(text))){if(match.index>last)parts.push(text.slice(last,match.index));const key=parts.length;parts.push(match[1]?<strong key={key}>{match[1]}</strong>:match[2]?<em key={key}>{match[2]}</em>:<a key={key} href={match[4]} target="_blank" rel="noreferrer">{match[3]}</a>);last=pattern.lastIndex;}
 if(last<text.length)parts.push(text.slice(last));return parts;
}
/** Text block formatting from the editor toolbar: **bold**, *italic*, ## heading, - list, [link](https://…). */
export function RichText({text}:{text:string}){
 const out:ReactNode[]=[];let para:string[]=[],list:string[]=[];
 const flush=()=>{if(para.length)out.push(<p key={out.length} style={{whiteSpace:'pre-wrap'}}>{inline(para.join('\n'))}</p>);if(list.length)out.push(<ul key={out.length} className="a-list">{list.map((item,i)=><li key={i}>{inline(item)}</li>)}</ul>);para=[];list=[];};
 for(const line of text.split('\n')){const item=/^[-•]\s+(.*)$/.exec(line),heading=/^##\s+(.*)$/.exec(line);if(item){if(para.length)flush();list.push(item[1]);}else if(heading){flush();out.push(<h3 key={out.length} className="h3">{inline(heading[1])}</h3>);}else if(!line.trim())flush();else{if(list.length)flush();para.push(line);}}
 flush();return <>{out}</>;
}
const BlockIcon=({name}:{name?:string})=>{const Icon=icons[name as keyof typeof icons] ?? Heart;return <Icon size={26} aria-hidden="true"/>;};
function MiniQuiz({item,index,block,lessonId,preview=false}:{item:Item;index:number;block:Block;lessonId:string;preview?:boolean}) {
  const [choice,setChoice]=useState<number|null>(null);
  const [feedback,setFeedback]=useState<{correct:boolean;explanation:string}|null>(null);
  const [pending,setPending]=useState(false);
  const [error,setError]=useState('');
  async function answer(selected:number) {
    setPending(true);setError('');
    try { const result=await api<{correct:boolean;explanation:string}>((preview?`/api/v1/coord/learning/lessons/${lessonId}/preview/quiz/${block.id}`:`/api/v1/learning/lessons/${lessonId}/blocks/${block.id}/answer`),{method:'POST',body:{question_index:index,selected_option:selected},idempotencyKey:crypto.randomUUID()});setChoice(selected);setFeedback(result); }
    catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить ответ');}finally{setPending(false);}
  }
  return <div className="card a-quiz"><p className="a-q">{item.q}</p><div className="a-qopts">{item.o.map((option,i)=><button className={`a-qopt ${choice===i?(feedback?.correct?'is-right':'is-wrong'):''}`} disabled={pending||Boolean(feedback)} key={i} onClick={()=>void answer(i)}>{option}</button>)}</div>{error&&<p role="alert">{error}</p>}{feedback&&<div className={`a-fb ${feedback.correct?'is-ok':'is-bad'}`} role="status"><b>{feedback.correct?'Верно':'Не совсем'}</b><p>{feedback.explanation}</p></div>}</div>;
}
export function ContentBlock({block:b,lessonId,preview=false}:{block:Block;lessonId:string;preview?:boolean}) {
  const items=b.items??[];
  const head=b.title?<h2 className="h3 a-bt">{b.title}</h2>:null;
  switch(b.type) {
    case 'text':return <section>{head}<RichText text={b.text??''}/></section>;
    case 'image':return <figure className="a-image">{b.asset_id&&<img src={appPath(preview?`/api/v1/coord/learning/lessons/${lessonId}/assets/${b.asset_id}`:`/api/v1/learning/lessons/${lessonId}/assets/${b.asset_id}`)} alt={b.title||'Картинка к уроку'} loading="lazy"/>}{b.title&&<figcaption>{b.title}</figcaption>}</figure>;
    case 'sim':return <section className="card a-sim">{head??<h2 className="h3 a-bt">Тренажёр</h2>}<p>Потренируйтесь в разговоре с персонажем и получите разбор.</p>{b.scenario_id&&<Link className="btn btn-secondary" to={`/simulator/${b.scenario_id}`}>Открыть тренажёр</Link>}</section>;
    case 'task':return <section className="card">{head}<p>{b.text}</p>{b.required&&<p className="tag">Обязательное задание</p>}{preview&&<><Field label="Ваш ответ"><Textarea disabled placeholder="Здесь волонтёр отвечает на задание"/></Field><Button disabled>Сохранить ответ</Button></>}</section>;
    case 'file':return <section className="card">{head}{b.asset_id?<a href={appPath(preview?`/api/v1/coord/learning/lessons/${lessonId}/assets/${b.asset_id}`:`/api/v1/learning/lessons/${lessonId}/assets/${b.asset_id}`)} target="_blank" rel="noreferrer">Открыть материал</a>:<p>Материал ещё не загружен.</p>}</section>;
    case 'lead':return <p className="a-lead">{b.text}</p>;
    case 'facts':return <div className="a-facts">{(items as string[][]).map(([n,label],i)=><div className="kpi" key={i}><span className="kpi-num">{n}</span><span className="kpi-label">{label}</span></div>)}</div>;
    case 'timeline':return <div className="a-timeline">{(items as string[][]).map(([year,title,text],i)=><div className="a-tl" key={i}><span className="a-dotline"/><span className="a-year">{year}</span><div className="a-tlcard"><h3>{title}</h3><p>{text}</p></div></div>)}</div>;
    case 'icards':return <section>{head}<div className="a-icards">{(items as Item[]).map((item,i)=><div className={`a-icard a-tint-${i%4}`} key={i}><span className="a-ico"><BlockIcon name={item.icon}/></span><h3>{item.title}</h3><p>{item.text}</p></div>)}</div></section>;
    case 'story':return <section className="a-story">{head}<p>{b.intro}</p><div className="a-storyrow">{(items as string[][]).map(([title,text,icon],i)=><div className={`a-stage a-tint-${i%4}`} key={i}><BlockIcon name={icon}/><b>{title}</b><p>{text}</p></div>)}</div></section>;
    case 'rules':return <section className="card">{head}<ol className="a-rules">{(items as string[]).map((text,i)=><li className="a-rule" key={i}><span className="a-rn" aria-hidden="true">{i+1}</span><p>{text}</p></li>)}</ol></section>;
    case 'phrases':return <section>{head}<div className="a-phr-head"><span>Так говорим</span><span>Так не говорим</span></div>{(items as string[][]).map(([say,avoid],i)=><div className="a-phr" key={i}><span className="a-yes">{say}</span><span className="a-no">{avoid}</span></div>)}</section>;
    case 'quiz':return <section>{head}{(items as Item[]).map((item,i)=><MiniQuiz key={i} item={item} index={i} block={b} lessonId={lessonId} preview={preview}/>)}</section>;
    case 'video':return <figure className="a-video">{isVideoEmbed(b.embed_url)?<div className="a-embed"><iframe src={b.embed_url} title={b.title||'Видео'} loading="lazy" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"/></div>:b.asset_id?<MediaVideo src={appPath(preview?`/api/v1/coord/learning/lessons/${lessonId}/assets/${b.asset_id}`:`/api/v1/learning/lessons/${lessonId}/assets/${b.asset_id}`)}/>:<div className="a-vbox"><span aria-hidden="true">▶</span><span>Видео скоро появится</span></div>}<figcaption><b>{b.title}</b> <span>{b.duration}</span></figcaption></figure>;
    case 'callout':return <p className={`learning-callout ${b.tone==='warn'?'is-warning':''}`}><AlertCircle size={22} aria-hidden="true"/>{b.text}</p>;
    default:return <p role="alert">Этот блок пока не поддерживается.</p>;
  }
}
export function TopicBlocks({blocks,lessonId}:{blocks:Block[];lessonId:string}) {
 const [open,setOpen]=useState(0),[seen,setSeen]=useState<number[]>([]);
 const titles:Record<string,string>={facts:'Фонд в цифрах',timeline:'Как всё начиналось',callout:'Важно',rules:'Пять правил',quiz:'Проверьте себя',lead:'Коротко'};
 return <div className="l-list card">{blocks.map((block,i)=><section className={`l-item ${open===i?'is-open':''}`} key={block.id}><button className="l-head" aria-expanded={open===i} onClick={()=>setOpen(open===i?-1:i)}><span className="l-mark">{seen.includes(i)?'✓':i+1}</span><span>{block.title||titles[block.type]||'Тема'}</span><span className="grow"/><span aria-hidden="true">⌄</span></button>{open===i&&<div className="l-body"><ContentBlock block={block} lessonId={lessonId}/><Button variant="primary" onClick={()=>{setSeen([...seen,i]);setOpen(i+1);}}>Понятно</Button></div>}</section>)}</div>;
}

function MediaVideo({src}:{src:string}){
 const ref=useRef<HTMLVideoElement>(null),seek=useRef(0);const [failed,setFailed]=useState(false),[loading,setLoading]=useState(true);
 return <div>{loading&&!failed&&<p role="status">Загружаем видео…</p>}<video ref={ref} controls preload="metadata" src={src} onTimeUpdate={event=>{seek.current=event.currentTarget.currentTime;}} onLoadedMetadata={event=>{event.currentTarget.currentTime=Math.min(seek.current,event.currentTarget.duration||seek.current);setLoading(false);}} onError={()=>{setFailed(true);setLoading(false);}}/>{failed&&<div role="alert"><p>Не удалось загрузить видео. Проверьте соединение и попробуйте ещё раз.</p><Button variant="secondary" onClick={()=>{setFailed(false);setLoading(true);ref.current?.load();}}>Загрузить снова</Button></div>}</div>;
}
