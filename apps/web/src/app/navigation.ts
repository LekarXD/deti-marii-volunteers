import {enabledDestinations} from './featureAvailability';
import type {IconName} from '../ui/Icon';
export interface NavigationLink {label:string;to:string;icon?:IconName;}
export interface NavigationGroup {label:string;icon:IconName;links:NavigationLink[];}
export const candidateNavigation:NavigationLink[]=[{label:'Главная',to:'/home'},{label:'Личный кабинет',to:'/application'},{label:'Знакомство с фондом',to:'/onboarding'},{label:'Направления',to:'/opportunities'},{label:'Мои занятия',to:'/my/assignments'},{label:'Обучение',to:'/academy'},{label:'Сообщения',to:'/messages'},{label:'Вопрос наставнику',to:'/mentor'},{label:'Тренажёр',to:'/simulator'},{label:'Вебинары',to:'/webinars'}].filter(link=>enabledDestinations.has(link.to));
/** Presentation availability only: the router/server still authorize each route. */
export function getCandidateNavigation(verified:boolean) {
 const items=candidateNavigation.filter(link=>verified?link.to!=='/application':link.to!=='/home');
 const primary=items.filter(link=>['/home','/application','/onboarding','/opportunities'].includes(link.to));
 return {items,primary,more:items.filter(link=>!primary.includes(link))};
}
export const candidatePrimaryNavigation=getCandidateNavigation(false).primary;
export const candidateMoreNavigation=getCandidateNavigation(false).more;
/** A top-level coordinator section; its pages are the section tabs listed in app/sectionTabs.ts. */
export interface NavigationSection {label:string;to:string;icon:IconName;/** Path prefixes that light the section up. */match:string[];}
const under=(path:string,prefix:string)=>prefix==='/fund'?path==='/fund':path===prefix||path.startsWith(`${prefix}/`);
/** First integrated destination of a section, in the order of its prefixes. */
const landing=(item:NavigationSection)=>item.match.flatMap(prefix=>[...enabledDestinations].filter(path=>under(path,prefix)).sort((a,b)=>a.length-b.length)).at(0);
const enabled=(item:NavigationSection)=>landing(item)!==undefined;
/** Five sections without dropdowns; messages and signals are icons on the right, rare pages sit in the profile menu. */
export const coordinatorSections:NavigationSection[]=([
 {label:'Обзор',to:'/fund',icon:'chart',match:['/fund']},
 {label:'Волонтёры',to:'/fund/candidates',icon:'users',match:['/fund/candidates','/fund/interviews','/fund/volunteers','/fund/prizes']},
 {label:'Мероприятия',to:'/fund/opportunities',icon:'calendar',match:['/fund/opportunities','/fund/responses','/fund/schedule','/fund/events','/fund/roles']},
 {label:'Подопечные',to:'/fund/participants',icon:'heart',match:['/fund/participants','/fund/groups']},
 {label:'Обучение',to:'/fund/learning',icon:'academy',match:['/fund/learning','/fund/webinars','/fund/recordings','/fund/knowledge','/fund/scenarios','/fund/simulator']},
] as NavigationSection[]).filter(enabled).map(section=>({...section,to:landing(section)??section.to}));
export const coordinatorShortcuts:NavigationSection[]=([
 {label:'Сообщения',to:'/fund/messages',icon:'message',match:['/fund/messages','/fund/notifications']},
 {label:'Сигналы',to:'/fund/signals',icon:'bell',match:['/fund/signals']},
] as NavigationSection[]).filter(enabled);
export const coordinatorAccountLinks:NavigationLink[]=[{label:'Рассылки',to:'/fund/notifications'},{label:'Отчёты',to:'/fund/reports'},{label:'Перенос в Добро.рф',to:'/fund/integrations/dobro/transfers'},{label:'Запросы на данные',to:'/fund/data-requests'},{label:'Настройки',to:'/fund/admin'}].filter(link=>enabledDestinations.has(link.to));
/** The section a staff path belongs to: the longest matching prefix wins, «Обзор» only on /fund itself. */
export function coordinatorSectionOf(path:string){return [...coordinatorSections,...coordinatorShortcuts].map(section=>({section,length:Math.max(-1,...section.match.filter(prefix=>under(path,prefix)).map(prefix=>prefix.length))})).filter(row=>row.length>=0).sort((a,b)=>b.length-a.length)[0]?.section;}

/** Current volunteer shell, limited to integrated routes with no invented detail context. */
export const volunteerNavigation:NavigationGroup[]=[
 {label:'Возможности',icon:'search',links:[{label:'Мероприятия',to:'/events'},{label:'Направления фонда',to:'/opportunities'},{label:'Моё участие',to:'/my/assignments'}]},
 {label:'Смены',icon:'calendar',links:[{label:'Мои смены',to:'/my/schedule'}]},
 {label:'Академия',icon:'academy',links:[{label:'Курсы',to:'/academy'},{label:'Тренажёр',to:'/simulator'},{label:'Вебинары',to:'/webinars'}]},
 {label:'Ещё',icon:'settings',links:[{label:'Сообщения',to:'/messages'},{label:'Мой путь',to:'/hours'},{label:'Профиль',to:'/profile'},{label:'ИИ-наставник',to:'/mentor'},{label:'Знакомство с фондом',to:'/onboarding'}]},
].map(group=>({...group,icon:group.icon as IconName,links:group.links.filter(link=>enabledDestinations.has(link.to))})).filter(group=>group.links.length>0);
