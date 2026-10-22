import type {HTMLAttributes,ReactNode} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {cx} from './controls';

export interface SectionTab {label:string;to:string;/** Other path prefixes that belong to this tab, e.g. a detail page. */also?:string[];}

const under=(path:string,prefix:string)=>path===prefix||path.startsWith(`${prefix}/`);

/** Sibling pages of one menu section shown as the page title: the current one is the h1, the others are links. */
export function SectionTabs({label,tabs,actions,className}:{label:string;tabs:SectionTab[];actions?:ReactNode;className?:string}){
 const {pathname}=useLocation();
 const best=tabs.map(tab=>({tab,length:Math.max(-1,...[tab.to,...(tab.also??[])].filter(prefix=>under(pathname,prefix)).map(prefix=>prefix.length))})).sort((a,b)=>b.length-a.length)[0];
 const current=best&&best.length>=0?best.tab:undefined;
 return <div className={cx('page-head section-tabs-head',className)}>
  <nav className="title-tabs" aria-label={label}>{tabs.map(tab=>tab===current?<h1 key={tab.to} aria-current="page">{tab.label}</h1>:<Link key={tab.to} to={tab.to}>{tab.label}</Link>)}</nav>
  {actions&&<div className="page-actions">{actions}</div>}
 </div>;
}

/** A page section whose heading keeps its distance from the card below it. */
export function PageSection({title,actions,children,className,...props}:{title:ReactNode;actions?:ReactNode;children?:ReactNode}&Omit<HTMLAttributes<HTMLElement>,'title'>){
 return <section {...props} className={cx('page-section',className)}>
  <div className="section-head"><h2 className="h2">{title}</h2>{actions}</div>
  {children}
 </section>;
}
