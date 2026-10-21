import {enabledDestinations} from './featureAvailability';
import type {IconName} from '../ui/Icon';
export interface NavigationLink {label:string;to:string;icon?:IconName;}
export interface NavigationGroup {label:string;icon:IconName;links:NavigationLink[];}
export const candidateNavigation:NavigationLink[]=[{label:'Личный кабинет',to:'/application'},{label:'Знакомство с фондом',to:'/onboarding'},{label:'Направления',to:'/opportunities'}].filter(link=>enabledDestinations.has(link.to));
const allCoordinatorNavigation:NavigationGroup[]=[
 {label:'Волонтёры',icon:'users',links:[{label:'Кандидаты',to:'/fund/candidates'},{label:'Собеседования',to:'/fund/interviews'},{label:'Волонтёры',to:'/fund/volunteers'},{label:'Проверка контактов',to:'/fund/contacts/review'}]},
 {label:'Занятия',icon:'calendar',links:[{label:'Расписание',to:'/fund/schedule'},{label:'Возможности',to:'/fund/opportunities'},{label:'Роли',to:'/fund/roles'}]},
 {label:'Участники',icon:'heart',links:[{label:'Участники',to:'/fund/participants'},{label:'Группы',to:'/fund/groups'}]},
 {label:'Ещё',icon:'settings',links:[{label:'Обучение',to:'/fund/learning'},{label:'База знаний',to:'/fund/knowledge'},{label:'Тренажёр',to:'/fund/scenarios'},{label:'Сигналы',to:'/fund/signals'},{label:'Отчёты',to:'/fund/reports'},{label:'Настройки',to:'/fund/settings'}]},
];
export const coordinatorNavigation=allCoordinatorNavigation.map(group=>({...group,links:group.links.filter(link=>enabledDestinations.has(link.to))})).filter(group=>group.links.length>0);
