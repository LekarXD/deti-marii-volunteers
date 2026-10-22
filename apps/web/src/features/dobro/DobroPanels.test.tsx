// @vitest-environment jsdom
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {DobroMyPath} from './DobroMyPath';
import {OpportunityDobroPanel} from './OpportunityDobroPanel';
import {DobroSettingsPanel} from './DobroSettingsPanel';
import {DobroOverviewTask} from './DobroOverviewTask';
const test=vi.hoisted(()=>({data:{} as unknown,mutate:vi.fn(async(_path:string,_method:string,_body:unknown)=>({}))}));
vi.mock('./api',async original=>{
 const real=await original<typeof import('./api')>();
 return {...real,useDobroQuery:()=>({data:test.data,isPending:false,error:null,refetch:vi.fn()}),useDobroCommand:(path:string,method='POST')=>({isPending:false,error:null,mutateAsync:(body:unknown)=>test.mutate(path,method,body)})};
});
const activity={id:'activity',opportunity_id:'opportunity',url:'https://dobro.ru/',title:'Вымышленное дело',kind:'long_term',valid_from:'2026-08-01',valid_until:'2027-05-31',version:1,can_edit:true};
beforeEach(()=>test.mutate.mockClear());
afterEach(cleanup);
describe('Dobro panels stay optional and truthful',()=>{
 it('records only the volunteer declaration and never blocks participation',async()=>{
  test.data={profile_url:'',profile_version:0,registration_url:'',verified_organization:false,total_minutes:120,entered_hours:0,hours_due:2,rules_note:'Перенос вручную',activities:[{activity,state:'none',enrollment_version:0,eligible_minutes:120,entered_hours:0,hours_due:2,carry_minutes:0,can_apply:true}]};
  render(<MemoryRouter><DobroMyPath/></MemoryRouter>);
  expect(test.mutate).not.toHaveBeenCalled();
  expect(screen.getByRole('heading',{name:'Книжка Добро.рф'})).toBeTruthy();
  expect(screen.getByText('Чтобы часы попали в книжку, откликнись один раз на доброе дело фонда.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Откликнуться'}));
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(screen.getByText(/Участие в занятиях доступно независимо/)).toBeTruthy();
  expect(screen.getByRole('link',{name:'Откликнуться на Добро.рф'}).getAttribute('href')).toBe('https://dobro.ru/');
  expect(screen.queryByText('Выгрузить')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Я откликнулся'}));
  await waitFor(()=>expect(test.mutate).toHaveBeenCalledWith('/me/dobro-enrollments/activity','POST',{state:'applied',expected_version:0}));
  expect(test.mutate.mock.calls).toHaveLength(1);
 });
 it('lets the volunteer say the book is not needed, only after a confirmation',async()=>{
  test.data={profile_url:'',profile_version:0,registration_url:'',verified_organization:false,total_minutes:120,entered_hours:0,hours_due:2,rules_note:'',activities:[{activity,state:'none',enrollment_version:3,eligible_minutes:120,entered_hours:0,hours_due:2,carry_minutes:0,can_apply:true}]};
  render(<MemoryRouter><DobroMyPath/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'Мне не нужно'}));
  expect(screen.getByRole('dialog',{name:'Не переносить часы?'})).toBeTruthy();expect(test.mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Да, мне это не нужно'}));
  await waitFor(()=>expect(test.mutate).toHaveBeenCalledWith('/me/dobro-enrollments/activity','POST',{state:'not_needed',expected_version:3}));
 });
 it('shows what is already in the book and what moves at the start of next month',()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2026-10-22T12:00:00+03:00'));
  try{
   test.data={profile_url:'https://dobro.ru/volunteers/42',profile_version:1,registration_url:'',verified_organization:false,total_minutes:2760,entered_hours:38,hours_due:8,rules_note:'',activities:[{activity,state:'approved',enrollment_version:2,eligible_minutes:2760,entered_hours:38,hours_due:8,carry_minutes:0,can_apply:true}]};
   const {rerender}=render(<MemoryRouter><DobroMyPath/></MemoryRouter>);
   expect(screen.getByText('38 ч')).toBeTruthy();expect(screen.getByText('уже внесли')).toBeTruthy();expect(screen.getByText('8 ч')).toBeTruthy();expect(screen.getByText('за октябрь, перенесём в начале ноября')).toBeTruthy();
   expect(screen.getByRole('link',{name:'Открыть Добро.рф'}).getAttribute('href')).toBe('https://dobro.ru/volunteers/42');expect(screen.queryByText(/откликнись/)).toBeNull();
   test.data={profile_url:'',profile_version:0,registration_url:'',verified_organization:false,total_minutes:0,entered_hours:0,hours_due:0,rules_note:'',activities:[]};
   rerender(<MemoryRouter><DobroMyPath/></MemoryRouter>);
   expect(screen.queryByRole('heading',{name:'Книжка Добро.рф'})).toBeNull();
  }finally{vi.useRealTimers();}
 });
 it('edits an unused link through its own versioned endpoint',async()=>{
  test.data=[activity];
  render(<MemoryRouter><OpportunityDobroPanel opportunityId="opportunity"/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'Редактировать'}));
  fireEvent.change(screen.getByLabelText('Ссылка на доброе дело'),{target:{value:'https://dobro.ru/event/123'}});
  fireEvent.click(screen.getByRole('button',{name:'Сохранить ссылку'}));
  await waitFor(()=>expect(test.mutate).toHaveBeenCalledWith('/fund/opportunities/opportunity/dobro/activity','PUT',expect.objectContaining({url:'https://dobro.ru/event/123',expected_version:1})));
 });
 it('starts without organization verification or automated reminders',()=>{
  test.data={version:0,organization_url:'',registration_url:'',verified:false,monthly_day:5,hard_deadline_days:60,risk_days:7,rules_confirmed:false,reminders_enabled:false,reminder_template:'{имя}: {ссылка}',rules_note:'Целые часы; остаток минут сохраняется.'};
  render(<MemoryRouter><DobroSettingsPanel/></MemoryRouter>);
  expect((screen.getByRole('checkbox',{name:'Фонд верифицирован на Добро.рф'}) as HTMLInputElement).checked).toBe(false);
  expect((screen.getByRole('checkbox',{name:'Напоминать мне в Опоре о ежемесячном переносе и сроках'}) as HTMLInputElement).checked).toBe(false);
  expect(screen.getByText('Без API, координатор переносит часы вручную')).toBeTruthy();
  expect(test.mutate).not.toHaveBeenCalled();
 });
 it('tells the coordinator which month, how much and by when to enter in Dobro',()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2026-10-22T12:00:00+03:00'));
  try{
   test.data={period:'2026-10',groups:[],total_hours_due:9,total_people:2,work_deadline:'2026-11-05',at_risk_count:3,rules_note:''};
   const {rerender}=render(<MemoryRouter><DobroOverviewTask/></MemoryRouter>);
   expect(screen.getByRole('heading',{name:'Внести часы за октябрь в Добро.рф'})).toBeTruthy();
   expect(screen.getByText('9 часов у 2 человек. Внесите их до 5 ноября.')).toBeTruthy();
   expect(screen.getByText('Срочно: 3 записи с близким или пропущенным крайним сроком')).toBeTruthy();
   expect(screen.getByRole('link',{name:'Открыть список'}).getAttribute('href')).toBe('/fund/integrations/dobro/transfers?period=2026-10');
   test.data={period:'2026-10',groups:[],total_hours_due:0,total_people:0,work_deadline:'2026-11-05',at_risk_count:0,rules_note:''};
   rerender(<MemoryRouter><DobroOverviewTask/></MemoryRouter>);
   expect(screen.getByText('За октябрь вносить нечего: часы уже отмечены или участий пока не было.')).toBeTruthy();
   expect(screen.queryByText(/Срочно/)).toBeNull();
  }finally{vi.useRealTimers();}
 });
});
