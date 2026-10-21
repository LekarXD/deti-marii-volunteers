export type FormOption = string | {label:string;icon?:string};
export type Condition = {field:string;value:string|string[]};
export type FormField = {id:string;label:string;type:string;required?:boolean;optional?:boolean;half?:boolean;placeholder?:string;autocomplete?:string;mask?:string;why?:string;options?:FormOption[];exclusive?:string[];allowOther?:boolean;showIf?:Condition;groups?:{title:string;showIf?:Condition;options:FormOption[]}[]};
export type FormContent = {title:string;intro:string;path:{icon:string;title:string;meta:string}[];pathNote:string;steps:{id:string;title:string;fields:FormField[]}[];shortNames:Record<string,string>};
export type Answers = Record<string, string | string[] | boolean>;
export function visible(condition:Condition|undefined, answers:Answers):boolean {
  if(!condition)return true;
  const actual=answers[condition.field], expected=Array.isArray(condition.value)?condition.value:[condition.value];
  return (Array.isArray(actual)?actual:[actual]).some(value=>typeof value==='string'&&expected.includes(value));
}
export const label=(option:FormOption)=>typeof option==='string'?option:option.label;
export function masked(value:string, mask?:string) {
  if(mask==='phone') {
    let digits=value.replace(/\D/g,''); if(digits.startsWith('8'))digits='7'+digits.slice(1); if(digits&&!digits.startsWith('7'))digits='7'+digits;
    digits=digits.slice(0,11);const rest=digits.slice(1);
    return digits?'+7'+(rest?' ('+rest.slice(0,3):'')+(rest.length>=3?') ':'')+rest.slice(3,6)+(rest.length>6?'-'+rest.slice(6,8):'')+(rest.length>8?'-'+rest.slice(8,10):''):'';
  }
  if(mask==='date') {const d=value.replace(/\D/g,'').slice(0,8);return d.slice(0,2)+(d.length>2?'.'+d.slice(2,4):'')+(d.length>4?'.'+d.slice(4):'');}
  if(mask==='telegram')return value?'@'+value.replace(/^@+/,'').replace(/[^A-Za-z0-9_]/g,'').slice(0,32):'';
  if(mask==='name')return value.replace(/(^|[\s-])\p{L}/gu,letter=>letter.toLocaleUpperCase('ru'));
  return value;
}
export function displayDate(value:string) {return /^\d{4}-\d{2}-\d{2}$/.test(value)?value.split('-').reverse().join('.'):value;}
