// @vitest-environment jsdom
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {DobroMyPath} from './DobroMyPath';
import {OpportunityDobroPanel} from './OpportunityDobroPanel';
import {DobroSettingsPanel} from './DobroSettingsPanel';
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
  fireEvent.click(screen.getByRole('button',{name:/Вымышленное дело — Нужен отклик/}));
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(screen.getByText(/Участие в занятиях доступно независимо/)).toBeTruthy();
  expect(screen.getByRole('link',{name:'Откликнуться на Добро.рф'}).getAttribute('href')).toBe('https://dobro.ru/');
  expect(screen.queryByText('Выгрузить')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Я откликнулся'}));
  await waitFor(()=>expect(test.mutate).toHaveBeenCalledWith('/me/dobro-enrollments/activity','POST',{state:'applied',expected_version:0}));
  expect(test.mutate.mock.calls).toHaveLength(1);
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
});
