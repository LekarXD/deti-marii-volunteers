import type {SectionTab} from '../ui';

/** Pages of one coordinator menu section; each page shows them as its title (SectionTabs). */
export const volunteersTabs:SectionTab[]=[
 {label:'Кандидаты',to:'/fund/candidates'},
 {label:'Собеседования',to:'/fund/interviews'},
 {label:'Все волонтёры',to:'/fund/volunteers'},
 {label:'Призы',to:'/fund/prizes'},
];
export const eventsTabs:SectionTab[]=[
 {label:'Мероприятия',to:'/fund/opportunities',also:['/fund/responses']},
 {label:'Расписание',to:'/fund/schedule',also:['/fund/events']},
 {label:'Роли',to:'/fund/roles'},
];
export const wardsTabs:SectionTab[]=[
 {label:'Подопечные',to:'/fund/participants'},
 {label:'Группы',to:'/fund/groups'},
];
export const learningTabs:SectionTab[]=[
 {label:'Курсы',to:'/fund/learning'},
 {label:'Эфиры и записи',to:'/fund/webinars',also:['/fund/recordings']},
 {label:'База знаний',to:'/fund/knowledge'},
 {label:'Тренажёр',to:'/fund/scenarios',also:['/fund/simulator']},
];
