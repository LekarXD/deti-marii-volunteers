import {useId,useState} from 'react';
import {Button,Input} from '../../ui';
import type {Requirement} from './api';
/** Preparation as checkboxes: items already known to the fund plus the coordinator's own; a new item is recommended, never blocking. */
export function PreparationEditor({value,options=[],onChange,legend='До первого выхода'}:{value:Requirement[];options?:Requirement[];onChange:(value:Requirement[])=>void;legend?:string}){
 const [own,setOwn]=useState(''),[added,setAdded]=useState<Requirement[]>([]),id=useId();
 const items=Array.from(new Map([...options,...added,...value].map(item=>[item.key,item])).values()),on=(key:string)=>value.some(item=>item.key===key);
 function add(){const title=own.trim();if(!title)return;const known=items.find(item=>item.title.toLocaleLowerCase('ru')===title.toLocaleLowerCase('ru')),item=known??{key:crypto.randomUUID(),title,level:'recommended' as const};if(!known)setAdded([...added,item]);if(!on(item.key))onChange([...value,item]);setOwn('');}
 return <fieldset className="field activity-prep-field"><legend className="label">{legend}</legend>
  {items.length>0&&<div className="prep">{items.map(item=><label key={item.key}><input type="checkbox" checked={on(item.key)} onChange={()=>onChange(on(item.key)?value.filter(r=>r.key!==item.key):[...value,item])}/>{item.title}</label>)}</div>}
  <div className="pick-add"><label className="sr-only" htmlFor={id}>Свой пункт подготовки</label><Input id={id} placeholder="Свой пункт" value={own} onChange={e=>setOwn(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add();}}}/><Button variant="secondary" size="sm" disabled={!own.trim()} onClick={add}>Добавить</Button></div>
 </fieldset>;
}
