// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import * as transport from '../../api/transport';
import type {TransferPeriod,TransferRow} from './model';
import {DobroTransferPage} from './DobroTransferPage';
const activity={can_edit:false,id:'10000000-0000-4000-8000-000000000001',opportunity_id:'10000000-0000-4000-8000-000000000002',url:'https://dobro.ru/event/1',kind:'long_term' as const,title:'Учебное доброе дело',valid_from:'2026-09-01',valid_until:'2027-05-31',version:1};
const row:TransferRow={id:'10000000-0000-4000-8000-000000000003',user_id:'10000000-0000-4000-8000-000000000004',display_name:'Волонтёр Учебный',profile_url:'https://dobro.ru/volunteers/1',state:'applied',enrollment_version:2,minutes_in_period:610,eligible_minutes:490,capped_minutes:120,overlap_minutes:0,duration_trimmed_minutes:0,carry_minutes:10,entered_hours:0,hours_due:8,target_total_hours:8,correction_hours:0,hard_deadline:'2027-07-30',deadline_state:'risk',can_mark:true,historical:false,snapshot_hash:'1'.repeat(64),history:[],reminder_text:'Учебный текст со ссылкой https://dobro.ru/event/1'};
const fixture:TransferPeriod={period:'2026-10',groups:[{activity,rows:[row]}],total_hours_due:8,total_people:1,work_deadline:'2026-11-05',at_risk_count:1,rules_note:'Учебное правило: отметка координатора, не ответ Добро.рф.'};
let current:TransferPeriod,conflict=false,hold=false,release:(()=>void)|undefined;const clients:QueryClient[]=[];
beforeEach(()=>{current=structuredClone(fixture);conflict=false;hold=false;release=undefined;vi.spyOn(transport,'api').mockImplementation(async<T,>(path:string,options?:transport.ApiOptions):Promise<T>=>{
 if(path.startsWith('/fund/integrations/dobro/transfers?'))return current as T;
 if(path==='/fund/integrations/dobro/transfers/mark-entered'){
  if(conflict){conflict=false;current={...current,groups:[{activity,rows:[{...row,hours_due:7,snapshot_hash:'2'.repeat(64)}]}]};throw new transport.ApiError(409,'dobro_snapshot_changed','Факты изменились');}
  if(hold)await new Promise<void>(resolve=>{release=resolve;});
  const body=options?.body as {rows:{id:string;hours_delta:number}[]};current={...current,total_hours_due:0,groups:current.groups.map(group=>({...group,rows:group.rows.map(item=>{const marked=body.rows.find(value=>value.id===item.id);return marked?{...item,state:'approved' as const,hours_due:item.hours_due-marked.hours_delta,entered_hours:item.entered_hours+marked.hours_delta,history:[...item.history,{id:'journal',period:'2026-10',hours_delta:marked.hours_delta,minutes_due_snapshot:item.eligible_minutes,note:'',entered_at:'2026-11-01T12:00:00Z'}]}:item;})}))};return current as T;
 }
 if(path.includes('/enrollments/'))return {} as T;
 throw new Error('Unexpected manual-transfer API');
 });});
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.restoreAllMocks();vi.unstubAllGlobals();});
function view(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/integrations/dobro/transfers?period=2026-10']}><DobroTransferPage/></MemoryRouter></QueryClientProvider>);}
const writes=()=>vi.mocked(transport.api).mock.calls.filter(([,options])=>options?.method==='POST'||options?.method==='PUT');
it('renders authoritative hours and notes without writing or claiming external delivery',async()=>{
 view();await screen.findByText('К переносу 8 ч у 1 человека');expect(screen.getByText('Остаток: 10 мин')).toBeTruthy();expect(screen.getByText('Обрезано 2 ч: лимит 8 ч в сутки')).toBeTruthy();expect(writes()).toHaveLength(0);expect(document.querySelector('select')).toBeNull();expect(screen.getByRole('link',{name:'Открыть на Добро.рф'}).getAttribute('href')).toBe(activity.url);
});
it('stores an exact snapshot only after explicit manual confirmation and waits for the server receipt',async()=>{
 hold=true;view();const user=userEvent.setup();await user.click(await screen.findByRole('checkbox',{name:'Внесено вручную'}));const dialog=screen.getByRole('dialog',{name:'Подтвердить ручной перенос (1)'}),save=within(dialog).getByRole('button',{name:'Сохранить отметку'});expect(save.hasAttribute('disabled')).toBe(true);expect(writes()).toHaveLength(0);
 await user.click(within(dialog).getByRole('checkbox'));await user.click(save);await waitFor(()=>expect(writes()).toHaveLength(1));expect(screen.queryByText(/Отметка сохранена в журнале Опоры/)).toBeNull();expect(screen.getByRole('dialog')).toBeTruthy();
 expect(writes()[0][1]?.body).toEqual({confirmed:true,note:'',rows:[{id:row.id,user_id:row.user_id,activity_id:activity.id,period:'2026-10',snapshot_hash:row.snapshot_hash,hours_delta:8}]});release!();await screen.findByText(/Отметка сохранена в журнале Опоры/);expect(screen.getByText('Отклик одобрен')).toBeTruthy();expect(writes()).toHaveLength(1);
});
it('requires a correction reason and permits only a same-direction partial integer amount',async()=>{
 current={...fixture,total_hours_due:-2,groups:[{activity,rows:[{...row,state:'approved',hours_due:-2,correction_hours:2}]}]};view();const user=userEvent.setup();await user.click(await screen.findByRole('button',{name:'Отметить все внесёнными'}));const dialog=screen.getByRole('dialog'),input=within(dialog).getByLabelText(`Часы: ${row.display_name}`),consent=within(dialog).getByRole('checkbox');expect(consent.hasAttribute('disabled')).toBe(true);await user.type(within(dialog).getByLabelText('Причина исправления'),'Исправлен факт участия');await user.clear(input);await user.type(input,'1');expect(consent.hasAttribute('disabled')).toBe(true);await user.clear(input);await user.type(input,'-1');expect(consent.hasAttribute('disabled')).toBe(false);await user.click(consent);await user.click(within(dialog).getByRole('button',{name:'Сохранить отметку'}));await waitFor(()=>expect(writes()).toHaveLength(1));expect(writes()[0][1]?.body).toMatchObject({note:'Исправлен факт участия',rows:[{hours_delta:-1}]});
});
it('preserves the modal and note on changed facts and requires a refreshed snapshot plus new consent',async()=>{
 conflict=true;view();const user=userEvent.setup();await user.click(await screen.findByRole('checkbox',{name:'Внесено вручную'}));let dialog=screen.getByRole('dialog');await user.type(within(dialog).getByLabelText('Заметка (необязательно)'),'Проверено вручную');await user.click(within(dialog).getByRole('checkbox'));await user.click(within(dialog).getByRole('button',{name:'Сохранить отметку'}));await screen.findByText(/Расчёт изменился/);expect((screen.getByLabelText('Заметка (необязательно)') as HTMLTextAreaElement).value).toBe('Проверено вручную');expect(writes()).toHaveLength(1);
 await user.click(screen.getByRole('button',{name:'Обновить расчёт'}));await waitFor(()=>expect(screen.queryByRole('button',{name:'Обновить расчёт'})).toBeNull());dialog=screen.getByRole('dialog');expect((within(dialog).getByRole('checkbox') as HTMLInputElement).checked).toBe(false);expect(within(dialog).getByRole('button',{name:'Сохранить отметку'}).hasAttribute('disabled')).toBe(true);const amount=within(dialog).getByLabelText(`Часы: ${row.display_name}`);await user.clear(amount);await user.type(amount,'7');await user.click(within(dialog).getByRole('checkbox'));await user.click(within(dialog).getByRole('button',{name:'Сохранить отметку'}));await waitFor(()=>expect(writes()).toHaveLength(2));expect(writes()[1][1]?.body).toMatchObject({note:'Проверено вручную',rows:[{hours_delta:7,snapshot_hash:'2'.repeat(64)}]});
});
it('copies the actual reminder template without sending a message or silently approving a blocked row',async()=>{
 current={...fixture,groups:[{activity,rows:[{...row,state:'none',can_mark:false}]}]};view();const user=userEvent.setup();await user.click(await screen.findByRole('button',{name:'Напомнить'}));const dialog=screen.getByRole('dialog',{name:'Напоминание про Добро.рф'});expect((within(dialog).getByLabelText('Текст напоминания') as HTMLTextAreaElement).value).toBe(row.reminder_text);expect(writes()).toHaveLength(0);expect(screen.queryByRole('checkbox',{name:'Внесено вручную'})).toBeNull();
});

it('labels the daily cap, overlapping minutes and event-duration trimming separately',async()=>{
 current={...fixture,groups:[{activity,rows:[{...row,minutes_in_period:630,eligible_minutes:480,carry_minutes:0,overlap_minutes:10,duration_trimmed_minutes:20}]}]};view();await screen.findByText('Пересечение занятий: 10 мин не переносим');expect(screen.getByText('Выше длительности события: 20 мин')).toBeTruthy();expect(screen.getByText('Обрезано 2 ч: лимит 8 ч в сутки')).toBeTruthy();
});
it('copies only actionable current rows as a TSV through an explicit clipboard action',async()=>{
 view();const user=userEvent.setup(),clipboard=vi.spyOn(navigator.clipboard,'writeText').mockResolvedValue();await user.click(await screen.findByRole('button',{name:'Скопировать список'}));expect(clipboard).toHaveBeenCalledWith('ФИО\tЧасы\nВолонтёр Учебный\t8');expect(writes()).toHaveLength(0);
});
it('bulk confirmation contains only actionable rows and records their exact snapshots atomically',async()=>{
 const second={...row,id:'second',user_id:'second-user',display_name:'Второй Волонтёр',state:'approved' as const,hours_due:4,snapshot_hash:'2'.repeat(64)};
 current={...fixture,total_hours_due:12,total_people:2,groups:[{activity,rows:[row,second,{...row,id:'blocked',user_id:'blocked-user',state:'none',can_mark:false},{...row,id:'excluded',user_id:'excluded-user',state:'not_needed',can_mark:false}]}]};view();const user=userEvent.setup();await user.click(await screen.findByRole('button',{name:'Отметить все внесёнными'}));const dialog=screen.getByRole('dialog',{name:'Подтвердить ручной перенос (2)'});expect(within(dialog).getAllByRole('textbox')).toHaveLength(3);expect(writes()).toHaveLength(0);await user.click(within(dialog).getByRole('checkbox'));await user.click(within(dialog).getByRole('button',{name:'Сохранить отметку'}));await waitFor(()=>expect(writes()).toHaveLength(1));expect(writes()[0][1]?.body).toMatchObject({rows:[{id:row.id,snapshot_hash:row.snapshot_hash,hours_delta:8},{id:second.id,snapshot_hash:second.snapshot_hash,hours_delta:4}]});
});
