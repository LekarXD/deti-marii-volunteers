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
const allCoordinatorNavigation:NavigationGroup[]=[
 {label:'Волонтёры',icon:'users',links:[{label:'Кандидаты',to:'/fund/candidates'},{label:'Собеседования',to:'/fund/interviews'},{label:'Волонтёры',to:'/fund/volunteers'},{label:'Проверка контактов',to:'/fund/contacts/review'},{label:'Импорт контактов',to:'/fund/contacts/import'}]},
 {label:'События',icon:'calendar',links:[{label:'Расписание',to:'/fund/schedule'},{label:'Возможности',to:'/fund/opportunities'},{label:'Роли',to:'/fund/roles'}]},
 {label:'Подопечные',icon:'heart',links:[{label:'Участники',to:'/fund/participants'},{label:'Группы',to:'/fund/groups'}]},
 {label:'Ещё',icon:'settings',links:[{label:'Отклики',to:'/fund/responses'},{label:'Вебинары',to:'/fund/webinars'},{label:'Записи уроков',to:'/fund/recordings'},{label:'Сообщения',to:'/fund/messages'},{label:'Уведомления',to:'/fund/notifications'},{label:'Обучение',to:'/fund/learning'},{label:'База знаний',to:'/fund/knowledge'},{label:'Сценарии тренажёра',to:'/fund/scenarios'},{label:'Разбор попыток',to:'/fund/simulator/review'},{label:'Сигналы',to:'/fund/signals'},{label:'Отчёты',to:'/fund/reports'},{label:'Перенос в Добро.рф',to:'/fund/integrations/dobro/transfers'},{label:'Настройки',to:'/fund/admin'}]},
];
export const coordinatorNavigation=allCoordinatorNavigation.map(group=>({...group,links:group.links.filter(link=>enabledDestinations.has(link.to))})).filter(group=>group.links.length>0);

/** Current volunteer shell, limited to integrated routes with no invented detail context. */
export const volunteerNavigation:NavigationGroup[]=[
 {label:'Возможности',icon:'search',links:[{label:'Направления фонда',to:'/opportunities'},{label:'Моё участие',to:'/my/assignments'}]},
 {label:'Смены',icon:'calendar',links:[{label:'Мои смены',to:'/my/schedule'}]},
 {label:'Академия',icon:'academy',links:[{label:'Курсы',to:'/academy'},{label:'Тренажёр',to:'/simulator'},{label:'Вебинары',to:'/webinars'}]},
 {label:'Ещё',icon:'settings',links:[{label:'Сообщения',to:'/messages'},{label:'Мой путь',to:'/hours'},{label:'Профиль',to:'/profile'},{label:'ИИ-наставник',to:'/mentor'},{label:'Знакомство с фондом',to:'/onboarding'}]},
].map(group=>({...group,icon:group.icon as IconName,links:group.links.filter(link=>enabledDestinations.has(link.to))})).filter(group=>group.links.length>0);
