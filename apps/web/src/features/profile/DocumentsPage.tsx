import {useId,useState,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Button,DatePicker,ErrorState,Icon,LoadingState} from '../../ui';
import {Document,useHours,useProfileList,useProfileCommand,downloadAsset,requestLabels,dayMonth,shortHours,today} from './api';
import './profile.css';

const recipients=['Вуз','Работа','По месту требования'];
type Period='all'|'year'|'custom';
const failureText=(error:unknown)=>error instanceof Error&&error.message?error.message:'Не получилось. Проверь соединение и попробуй ещё раз.';

/** Only the hours certificate: it is generated at once from confirmed minutes, so it can be downloaded right away. */
export function CertificateForm({action,extra}:{action:'download'|'prepare';extra?:ReactNode}){
 const id=useId(),hours=useHours(),now=today(),year=now.slice(0,4);
 const [period,setPeriod]=useState<Period>('all'),[recipient,setRecipient]=useState(recipients[0]),[from,setFrom]=useState(year+'-01-01'),[until,setUntil]=useState(now),[failure,setFailure]=useState<unknown>(null);
 const create=useProfileCommand<Document>('/me/profile/documents');
 const first=(hours.data?.entries??[]).reduce<string|null>((min,entry)=>entry.delta_minutes>0&&(!min||entry.service_date<min)?entry.service_date:min,null)??now;
 const range=period==='all'?{from:first,until:now}:period==='year'?{from:year+'-01-01',until:now}:{from,until};
 const valid=!!range.from&&!!range.until&&range.from<=range.until&&range.until<=now&&!(period==='all'&&hours.isPending);
 const periods:[Period,string][]=[['all','За всё время'],['year',`${year} год`],['custom','Свой период']];
 async function submit(){
  setFailure(null);
  try{const doc=await create.mutateAsync({kind:'certificate',period_from:range.from,period_to:range.until,recipient});if(action==='download'&&doc.asset_id&&doc.state==='ready')await downloadAsset(doc.asset_id,'справка-о-часах.pdf');}
  catch(error){setFailure(error);}
 }
 return <>
  <div className="form-grid">
   <div className="field"><span className="label" id={id+'-period'}>За какой период</span><div className="pick" role="group" aria-labelledby={id+'-period'}>{periods.map(([key,label])=><button key={key} type="button" className={period===key?'is-on':undefined} aria-pressed={period===key} onClick={()=>setPeriod(key)}>{label}</button>)}</div></div>
   <div className="field"><span className="label" id={id+'-whom'}>Для кого</span><div className="pick" role="group" aria-labelledby={id+'-whom'}>{recipients.map(label=><button key={label} type="button" className={recipient===label?'is-on':undefined} aria-pressed={recipient===label} onClick={()=>setRecipient(label)}>{label}</button>)}</div></div>
   {period==='custom'&&<><DatePicker label="Начало периода" value={from} onChange={setFrom} max={until||now}/><DatePicker label="Конец периода" value={until} onChange={setUntil} min={from} max={now}/></>}
  </div>
  <div className="row wrap path-form-actions"><Button disabled={!valid} loading={create.isPending} onClick={()=>void submit()}>{action==='download'?<><Icon name="download"/>Скачать PDF</>:'Подготовить справку'}</Button>{extra}</div>
  {!!failure&&<p className="path-alert" role="alert">{failureText(failure)}</p>}
 </>;
}

export function CertificatesPage(){
 const list=useProfileList<Document>('documents','/me/profile/documents'),[failure,setFailure]=useState<unknown>(null);
 const docs=(list.data??[]).filter(doc=>doc.kind==='certificate');
 return <div className="path-page path-docs">
  <Link className="back" to="/hours"><Icon name="chevron-left"/>Мой путь</Link>
  <div className="page-head"><h1 className="h1">Справка о часах</h1></div>
  <section className="card"><CertificateForm action="download"/></section>
  <section className="sec">
   <div className="sec-head"><h2 className="h2">Мои документы</h2></div>
   <div className="card">
    {list.isPending?<LoadingState/>:list.error?<ErrorState error={list.error} retry={()=>void list.refetch()}/>:docs.length?<div className="rows">{docs.map(doc=>{const ready=doc.state==='ready'&&!!doc.asset_id,titleId='doc-'+doc.id;return <div className="rowi" key={doc.id}>
     <span className={'st '+(ready?'st-ok':doc.state==='rejected'?'st-off':'st-wait')} aria-label={requestLabels[doc.state]??doc.state}><Icon name={ready?'check':doc.state==='rejected'?'x':'clock'}/></span>
     <div className="grow"><span className="rowi-title" id={titleId}>{dayMonth(doc.period_from)} — {dayMonth(doc.period_to)}</span><span className="meta">{doc.recipient}{ready?', '+shortHours(doc.total_minutes):''}</span>{doc.public_response&&<span className="meta">{doc.public_response}</span>}</div>
     {ready&&<span className="rowi-end"><Button variant="secondary" size="sm" aria-describedby={titleId} onClick={()=>{setFailure(null);void downloadAsset(doc.asset_id!,'справка-о-часах.pdf').catch(setFailure);}}><Icon name="download"/>Скачать PDF</Button></span>}
    </div>;})}</div>:<p className="p path-empty">Готовых справок пока нет.</p>}
    {!!failure&&<p className="path-alert" role="alert">{failureText(failure)}</p>}
   </div>
  </section>
 </div>;
}

/** Kept for existing imports. Volunteers get only the hours certificate: thank-you letters were removed by product decision. */
export function DocumentsPanel(){return <section className="card prof-docs"><CertificateForm action="download"/></section>;}
