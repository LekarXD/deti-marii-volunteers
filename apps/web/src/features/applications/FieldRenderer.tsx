import {Field, Input, Textarea} from '../../ui';
import {FormField, Answers, label, visible, masked, displayDate} from './form';
export function FieldRenderer({field,answers,onChange,error}:{field:FormField;answers:Answers;onChange:(id:string,value:Answers[string])=>void;error?:string}) {
  if(!visible(field.showIf,answers))return null;
  const value=answers[field.id], id='application-'+field.id;
  const options=field.options||[];
  const selected=(item:string)=>Array.isArray(value)&&value.includes(item);
  const toggle=(item:string)=>{const old=Array.isArray(value)?value:[];
    onChange(field.id,selected(item)?old.filter(v=>v!==item):field.exclusive?.includes(item)?[item]:[...old.filter(v=>!field.exclusive?.includes(v)),item]);};
  const hint=field.why|| (field.optional?'По желанию':undefined);
  const chips=(opts:typeof options)=><div role="group" aria-label={field.label} aria-invalid={!!error} aria-describedby={error?`${id}-error`:undefined} className={'ap-options '+(field.type==='tiles'?'ap-tiles':'')}>{opts.map(option=>{const text=label(option);return <button key={text} type="button" className={'ap-option '+(selected(text)||value===text?'is-on':'')} aria-pressed={selected(text)||value===text} onClick={()=>field.type==='select'?onChange(field.id,text):toggle(text)}>{text}</button>;})}</div>;
  return <div className={field.half?'ap-field ap-half':'ap-field'} data-field={field.id}>
    <Field label={field.type==='consent'?<span className="sr-only">Согласие</span>:field.label+(field.required?' *':'')} htmlFor={id} hint={hint} error={error}>
      {field.type==='consent'?<label className="ap-check"><input id={id} type="checkbox" checked={value===true} onChange={e=>onChange(field.id,e.target.checked)}/><span>{field.label}</span></label>:
       field.type==='textarea'?<Textarea id={id} value={String(value||'')} onChange={e=>onChange(field.id,e.target.value)} maxLength={4000}/>:
       ['select','tiles'].includes(field.type)?chips(options):
       field.type==='chips'?<><div className="ap-skill-groups">{field.groups?.filter(group=>visible(group.showIf,answers)).map(group=><div key={group.title}><p className="ap-group-title">{group.title}</p>{chips(group.options)}</div>)}</div>{field.allowOther&&<Input id={id} aria-label="Другой навык" placeholder="Другой навык — введите и нажмите Enter" onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();const text=e.currentTarget.value.trim();if(text){toggle(text);e.currentTarget.value='';}}}}/>}{Array.isArray(value)&&value.filter(item=>!field.groups?.some(group=>group.options.map(label).includes(item))).map(item=><button className="ap-option is-on" key={item} type="button" onClick={()=>toggle(item)}>{item} ×</button>)}</>:
       <Input id={id} name={field.id} type={field.type==='email'?'email':'text'} inputMode={field.type==='date'?'numeric':field.type==='tel'?'tel':undefined} autoComplete={field.autocomplete} placeholder={field.type==='date'?'ДД.ММ.ГГГГ':field.placeholder} value={field.type==='date'?displayDate(String(value||'')):String(value||'')} onChange={e=>onChange(field.id,masked(e.target.value,field.type==='date'?'date':field.mask))} aria-invalid={!!error}/>}
    </Field>
  </div>;
}
