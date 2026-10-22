import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Icon,Segmented,cx} from '../../ui';
import {splitLine} from './scenario';

export function BackLink({to='/fund/scenarios',children='Тренажёр'}:{to?:string;children?:ReactNode}){return <Link className="back" to={to}><Icon name="chevron-left"/>{children}</Link>;}
/** A chat bubble; the child's stage direction in [brackets] goes on its own italic line. */
export function Bubble({line,mine=false}:{line:string;mine?:boolean}){const {dir,text}=splitLine(line);return <div className={cx('ch-group',mine&&'is-mine')}><div className="ch-stack"><p className="ch-bubble is-tail">{dir&&<><span className="stage-dir">{dir}</span><br/></>}{text}</p></div></div>;}
export function ScoreDots({value}:{value:number}){return <span className={cx('score',value===1&&'mid',value===0&&'low')} role="img" aria-label={`Оценка ${value} из 2`}><i className={value>=1?'on':''}/><i className={value>=2?'on':''}/></span>;}
export function ScorePick({title,value,onChange,disabled,note,miss}:{title:string;value:number|undefined;onChange:(value:0|1|2)=>void;disabled?:boolean;note?:ReactNode;miss?:boolean}){
 return <div className={cx('score-pick',miss&&'miss')}><span><span className="label">{title}</span>{note}</span><Segmented label={title} value={value===undefined?'':String(value)} options={['0','1','2'].map(option=>({value:option,label:option,disabled}))} onChange={option=>onChange(Number(option) as 0|1|2)}/></div>;
}
export function Toggle({on,label,onChange,disabled}:{on:boolean;label:string;onChange:(on:boolean)=>void;disabled?:boolean}){return <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} className={cx('toggle',on&&'is-on')} onClick={()=>onChange(!on)}/>;}
