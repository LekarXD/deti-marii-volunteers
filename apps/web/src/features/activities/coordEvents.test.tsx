// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {buildEventRows,eventWhen,recurrenceText} from './coordEvents';
import {StaffOpportunitiesPage} from './OpportunitiesPage';
import {StaffEventPage} from './StaffEventPage';
import type {CalendarOccurrence} from './calendarApi';
import type {Opportunity} from './api';

const mocks=vi.hoisted(()=>({command:vi.fn(),occurrences:[] as unknown[],opportunities:[] as unknown[],summary:undefined as unknown,team:[] as unknown[],responses:[] as unknown[],reserve:[] as unknown[],suggestions:[] as unknown[],occurrence:undefined as unknown}));
vi.mock('../../app/layouts/AppProviders',()=>({useSession:()=>({session:{permissions:['assignments.manage','schedule.manage','opportunities.manage','roles.manage']}})}));
vi.mock('./api',()=>({
 useActivityCommand:()=>({mutateAsync:mocks.command,isPending:false,isError:false}),
 useActivityHistory:()=>({data:undefined}),
 useOpportunity:()=>({data:undefined,isPending:false,isError:false}),
 useOpportunityList:()=>({data:undefined,isPending:true}),
 useStaffOpportunities:()=>({data:mocks.opportunities,isPending:false,isError:false,fetchStatus:'idle'}),
 useRoleTitles:()=>({data:{role:'Ассистент педагога'}}),
 useEventResponsesSummary:()=>({data:mocks.summary}),
 useAwaitingResponses:()=>({data:mocks.responses}),
 useEventTeam:()=>({data:mocks.team,isPending:false,isError:false,fetchStatus:'idle'}),
 useEventReserve:()=>({data:mocks.reserve}),
}));
vi.mock('./calendarApi',()=>({
 useOccurrenceWindow:()=>({data:mocks.occurrences,isPending:false,isError:false,fetchStatus:'idle'}),
 useSeriesList:()=>[{data:{id:'weekly',recurrence:{frequency:'weekly',weekdays:[5]}}}],
 useCalendarOccurrence:()=>({data:mocks.occurrence,isPending:false,isError:false}),
 useCalendarSeries:()=>({data:undefined,isPending:true}),
 useCalendarGroups:()=>({data:undefined}),
}));
vi.mock('./participationApi',async importOriginal=>({...(await importOriginal<typeof import('./participationApi')>()),useAssignmentSuggestions:()=>({data:mocks.suggestions,isPending:false,isError:false})}));
vi.mock('../dobro',()=>({OpportunityDobroPanel:()=>null,EventOpportunityPicker:()=>null,DobroTeamPanel:()=>null,DobroOneOffPreparation:()=>null}));
vi.mock('../dobro/api',()=>({useDobroQuery:()=>({data:{opportunity_id:'opp'}})}));
vi.mock('./Participation',()=>({AssignmentCard:()=>null,OpportunityParticipation:()=>null}));
vi.mock('./CalendarEditor',()=>({CalendarEditor:()=>null}));
vi.mock('./OpportunityEditor',()=>({OpportunityEditor:()=>null}));

const need=(id:string,required:number,confirmed=0,invited=0)=>({id,role_id:'role',role_version_id:'rv',role_title:id==='driver'?'Водитель':'Ассистент педагога',version:2,required,invited,confirmed,missing:Math.max(0,required-confirmed),preparation_requirements:[],approval_policy:'coordinator',points_multiplier:1});
const occurrence=(id:string,series:string,starts:string,needs=[need(`${id}-need`,4,1,2)],title='Арт-суббота'):CalendarOccurrence=>({id,version:1,series_id:series,series_version:1,origin_local_date:starts.slice(0,10),origin_local_time:'14:00',starts_at:starts,ends_at:new Date(Date.parse(starts)+4*3600e3).toISOString(),timezone:'Europe/Moscow',group_id:null,title,program:'opora-stage-synthetic-v1',kind:'activity',format:'onsite',location:'Грибаново',audience:'Группа «Подсолнухи»',status:'scheduled',has_override:false,staffing_needs:needs,allowed_actions:['edit']}) as CalendarOccurrence;
const opportunity=(id:string,state:string,regularity='regular'):Opportunity=>({id,title:`Направление ${id}`,role_ids:['role'],program:'opora-stage-synthetic-v1',audience:'',task:'Помогать',conditions:'',regularity,location:'Мастерская',schedule:'По субботам',format:'onsite',preparation_requirements:[],approval_policy:'coordinator',points_multiplier:1,version:1,state,allowed_actions:['update'],matching:{algorithm_version:'rules-v2',evidence:[],context_versions:{},reasons:[],missing_data:[],constraints:[]}}) as unknown as Opportunity;
const assignment=(id:string,user:string,name:string,status:string,origin='invitation',approved=true,needId='one-need')=>({id,version:3,user_id:user,display_name:name,occurrence_id:'one',staffing_need_id:needId,title:'Арт-суббота',role_title:'Ассистент педагога',starts_at:'2030-10-26T11:00:00Z',ends_at:'2030-10-26T15:00:00Z',timezone:'Europe/Moscow',location:'Грибаново',status,origin,occurrence_status:'scheduled',approved_at:approved?'2030-10-01T10:00:00Z':null,confirmed_at:status==='confirmed'?'2030-10-01T10:00:00Z':null,conditions_version:2,readiness:[],allowed_actions:[],history:origin==='self'?[{command:'sign_up',reason:'Люблю рисовать с ребятами.'}]:[],attendance:null});

function mount(node:React.ReactNode,path:string,route:string){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={node}/></Routes></MemoryRouter></QueryClientProvider>);}
afterEach(cleanup);
beforeEach(()=>{mocks.command.mockReset().mockResolvedValue({status:'confirmed'});mocks.responses=[];mocks.reserve=[];mocks.suggestions=[];mocks.summary=undefined;});

it('maps dated events, a weekly series and opportunities without dates to the list rows',()=>{
 const now=Date.parse('2030-10-20T10:00:00Z');
 const rows=buildEventRows({now,occurrences:[occurrence('one','single','2030-10-26T11:00:00Z'),occurrence('w1','weekly','2030-10-26T09:00:00Z',[need('w1-need',2,1)],'Живопись'),occurrence('w2','weekly','2030-11-02T09:00:00Z',[need('w2-need',2)],'Живопись'),occurrence('old','gone','2030-10-10T11:00:00Z')],
  opportunities:[opportunity('pub','published'),opportunity('draft','draft','once'),opportunity('closed','closed')],summary:{sign_ups:[{occurrence_id:'one',staffing_need_id:'one-need',count:1},{occurrence_id:'w2',staffing_need_id:'w2-need',count:2}],responses:[{opportunity_id:'pub',count:3}]},
  rules:{weekly:{frequency:'weekly',weekdays:[5],exceptions:[]}},roleTitles:{role:'Ассистент педагога'}});
 const one=rows.find(row=>row.key==='one')!;
 expect(one).toMatchObject({tab:'open',section:'once',chip:'date',day:'26',mon:'окт',when:'Сб, 14:00–18:00, Грибаново',responses:1,to:'/fund/events/one'});
 expect(one.roles).toEqual([{name:'Ассистент педагога',fill:'2 из 4',low:false}]); // the pending own sign-up is not in the team yet
 expect(rows.find(row=>row.key==='series:weekly')).toMatchObject({section:'regular',chip:'repeat',when:'Каждую субботу, 12:00–16:00, Грибаново',responses:2,to:'/fund/events/w1'});
 expect(rows.find(row=>row.key==='old')).toMatchObject({tab:'past',responses:0});
 expect(rows.find(row=>row.key==='opportunity:pub')).toMatchObject({tab:'open',section:'regular',responses:3,when:'По субботам, Мастерская',roles:[{name:'Ассистент педагога'}]});
 expect(rows.find(row=>row.key==='opportunity:draft')).toMatchObject({tab:'draft',section:'once',chip:'undated'});
 expect(rows.find(row=>row.key==='opportunity:closed')?.tab).toBe('past');
 expect(rows.some(row=>row.when.includes('·'))).toBe(false);
});

it('words recurrences and multi-day dates without a middle dot',()=>{
 expect(recurrenceText({frequency:'weekly',weekdays:[2,5],exceptions:[]})).toBe('По средам и субботам');
 expect(recurrenceText({frequency:'biweekly',weekdays:[0],exceptions:[]})).toBe('Раз в две недели, по понедельникам');
 expect(eventWhen({starts_at:'2030-11-13T07:00:00Z',ends_at:'2030-11-15T15:00:00Z',timezone:'Europe/Moscow',location:'на Волге'})).toBe('13–15 ноября, на Волге');
 expect(eventWhen({starts_at:'2030-10-26T11:00:00Z',ends_at:'2030-10-26T15:00:00Z',timezone:'Europe/Moscow',location:'Грибаново'},true)).toBe('Сб, 26 октября, 14:00–18:00, Грибаново');
});

it('lists events with the waiting responses hero, tabs and «Показать все»',async()=>{
 const user=userEvent.setup();
 mocks.occurrences=['2030-10-26','2030-10-27','2030-10-28','2030-10-29','2030-10-30'].map((day,index)=>occurrence(`e${index}`,`s${index}`,`${day}T11:00:00Z`,[need(`e${index}-need`,4,index===0?0:3)],`Событие ${index+1}`));
 mocks.opportunities=[opportunity('pub','published'),opportunity('draft','draft','once')];
 mocks.summary={sign_ups:[{occurrence_id:'e1',staffing_need_id:'e1-need',count:2}],responses:[{opportunity_id:'pub',count:1}]};
 mount(<StaffOpportunitiesPage/>,'/fund/opportunities','/fund/opportunities');
 expect(screen.getByRole('heading',{level:1,name:'Мероприятия'})).toBeTruthy();
 expect(screen.getByRole('link',{name:'Расписание'})).toBeTruthy();
 expect(screen.getByRole('heading',{name:'3 отклика ждут ответа'})).toBeTruthy();
 expect(screen.getByText('Событие 2 и Направление pub')).toBeTruthy();
 expect(screen.getByRole('link',{name:'Разобрать отклики'}).getAttribute('href')).toBe('/fund/events/e1');
 expect(screen.getByRole('heading',{name:'Ближайшие'})).toBeTruthy();
 expect(screen.getByRole('heading',{name:'Регулярные занятия'})).toBeTruthy();
 expect(screen.queryByText('Событие 5')).toBeNull();
 expect(screen.getByText('2 отклика')).toBeTruthy();
 expect(screen.getByText('0 из 4').className).toBe('low');
 expect(document.body.textContent).not.toContain('opora-stage-synthetic-v1');
 await user.click(screen.getByRole('button',{name:'Показать все'}));
 expect(screen.getByText('Событие 5')).toBeTruthy();
 await user.click(screen.getByRole('radio',{name:'Черновики'}));
 expect(screen.getByText('Направление draft')).toBeTruthy();
 expect(screen.queryByText('Событие 1')).toBeNull();
 await user.type(screen.getByPlaceholderText('Название или место'),'нет такого');
 expect(screen.getByText('Ничего не нашли')).toBeTruthy();
},20000);

it('event page shows the team by role, answers a sign-up and invites a suggested volunteer',async()=>{
 const user=userEvent.setup();
 mocks.occurrence=occurrence('one','single','2030-10-26T11:00:00Z',[need('one-need',4,1,3),need('driver',1,1)]);
 mocks.team=[assignment('a1','u1','Анна Мальцева','confirmed'),assignment('a2','u2','Тимур Давыдов','invited'),assignment('a3','u3','Полина Гришина','invited','self',false),assignment('a4','u4','Олег Петров','confirmed','invitation',true,'driver')];
 mocks.responses=[{id:'r1',opportunity_id:'opp',opportunity_title:'Арт-суббота',user_id:'u5',display_name:'Ирина Лаптева',state:'submitted',decision_reason:'',version:1,allowed_actions:['approve'],history:[{state:'submitted',reason:'Я педагог начальных классов.'}]}];
 mocks.reserve=[{id:'res',version:1,user_id:'u6',display_name:'Сергей Миронов',occurrence_id:'one',staffing_need_id:'driver',role_title:'Водитель',state:'waiting',position:1}];
 mocks.suggestions=[{user_id:'u7',display_name:'Наталья Громова',reasons:['Подходит по навыку «Рисование»'],missing_data:[],facts:{attended:6},invitation_status:null}];
 mount(<StaffEventPage/>,'/fund/events/one','/fund/events/:id');
 expect(screen.getByRole('link',{name:'Мероприятия'}).getAttribute('href')).toBe('/fund/opportunities');
 expect(screen.getByText('Идёт набор, видно волонтёрам в ленте')).toBeTruthy();
 expect(screen.getByText('Сб, 26 октября, 14:00–18:00, Грибаново')).toBeTruthy();
 expect(screen.getByText('3 из 5 мест заняты')).toBeTruthy();
 expect(screen.getByText('2 из 4').className).toBe('cev-low');
 expect(screen.getAllByRole('img',{name:'Участие подтверждено'})).toHaveLength(2);
 expect(screen.getByText('ждём ответа')).toBeTruthy();
 expect(screen.getAllByText('Свободное место')).toHaveLength(2);
 expect(screen.getByText('Сергей Миронов')).toBeTruthy();
 expect(screen.queryByText(/Баллы/)).toBeNull();
 const panel=screen.getByRole('complementary');
 expect(within(panel).getByText('2')).toBeTruthy();
 expect(within(panel).getByText('Люблю рисовать с ребятами.')).toBeTruthy();
 await user.click(within(panel).getAllByRole('button',{name:'Принять'})[0]);
 expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({path:'/coord/assignments/a3/approve',body:expect.objectContaining({expected_version:3})}));
 await waitFor(()=>expect(within(panel).getByText('Полина в составе. Подтверждение ушло в сообщения')).toBeTruthy());
 await user.click(screen.getByRole('button',{name:'Пригласить волонтёров'}));
 expect(within(panel).getByRole('heading',{name:'Ассистент педагога'})).toBeTruthy();
 expect(within(panel).getByText('Подходят по роли и свободны 26 октября:')).toBeTruthy();
 await user.click(within(panel).getByRole('button',{name:'Пригласить'}));
 expect(mocks.command).toHaveBeenLastCalledWith(expect.objectContaining({path:'/coord/staffing-needs/one-need/invitations',body:{user_id:'u7',expected_version:2}}));
 await waitFor(()=>expect(within(panel).getByText('Приглашение отправлено')).toBeTruthy());
 await user.click(within(panel).getByRole('button',{name:'Вернуться к откликам'}));
 expect(within(panel).getByRole('heading',{name:'Отклики'})).toBeTruthy();
},20000);

it('offers the reserve when the role is full',async()=>{
 const user=userEvent.setup();
 mocks.occurrence=occurrence('one','single','2030-10-26T11:00:00Z',[need('one-need',1,1,1)]);
 mocks.team=[assignment('a1','u1','Анна Мальцева','confirmed'),assignment('a3','u3','Полина Гришина','invited','self',false)];
 mount(<StaffEventPage/>,'/fund/events/one','/fund/events/:id');
 await user.click(screen.getByRole('button',{name:'Мест нет — в резерв'}));
 expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({path:'/coord/staffing-needs/one-need/reserve',body:{expected_version:2,user_id:'u3',expected_assignment_version:3}}));
 await waitFor(()=>expect(screen.getByText('Полина в резерве')).toBeTruthy());
 await user.click(screen.getByRole('button',{name:'Отклонить'}));
 expect(mocks.command).toHaveBeenLastCalledWith(expect.objectContaining({path:'/coord/assignments/a3/cancel'}));
});
