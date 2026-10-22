import {NavLink} from 'react-router-dom';

/** «Мероприятия» is one section: own занятия, the whole feed and the fund's directions. */
const tabs=[{label:'Мои занятия',to:'/my/schedule'},{label:'Все мероприятия',to:'/events'},{label:'Направления фонда',to:'/opportunities'}];
export function EventsTabs(){return <nav className="subnav" aria-label="Мероприятия">{tabs.map(tab=><NavLink key={tab.to} to={tab.to} className={({isActive})=>isActive?'is-on':undefined}>{tab.label}</NavLink>)}</nav>;}
