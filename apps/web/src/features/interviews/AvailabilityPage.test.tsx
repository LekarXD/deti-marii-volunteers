// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import type {CalendarSlot} from './api';
import {AvailabilityPage,closeSlot} from './AvailabilityPage';

const mocks=vi.hoisted(()=>({run:vi.fn(),slots:[] as unknown[],windows:[] as unknown[]}));
vi.mock('./api',()=>({useCalendar:()=>({data:mocks.slots,isLoading:false}),useAvailability:()=>({data:mocks.windows}),useInterviewCommand:()=>({mutateAsync:mocks.run,reset:()=>{},isPending:false,error:null})}));
const minute=(t:string)=>Number(t.slice(0,2))*60+Number(t.slice(3));
const slot=(day:string,time:string,changes:Partial<CalendarSlot>={}):CalendarSlot=>{const start=new Date(`${day}T${time}:00+03:00`);return {starts_at:start.toISOString(),ends_at:new Date(start.getTime()+1800000).toISOString(),state:'free',series_id:`s-${day}-${time}`,series_version:2,recurrence:'once',timezone:'Europe/Moscow',origin_date:day,origin_minute:minute(time),window_start_minute:minute(time),window_end_minute:minute(time)+30,duration_minutes:30,buffer_after_minutes:0,venue:'Онлайн, Телемост',join_url:'https://telemost.example/x',booking_id:null,booking_status:null,candidate_name:null,...changes};};
const view=()=>render(<MemoryRouter><AvailabilityPage/></MemoryRouter>);
const cell=(name:string)=>screen.getByRole('button',{name});

beforeEach(()=>{vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2026-10-22T09:00:00Z'));mocks.run.mockReset();mocks.run.mockResolvedValue({});mocks.slots=[];mocks.windows=[];});
afterEach(()=>{cleanup();vi.useRealTimers();});

describe('free slots week grid',()=>{
 it('shows the Moscow week without legend numbers and keeps past cells inert',()=>{
  mocks.slots=[slot('2026-10-21','15:30')];
  view();
  expect(screen.getByRole('heading',{level:1,name:'Свободные слоты для собеседований'})).toBeTruthy();
  expect(screen.getByRole('link',{name:'Собеседования'}).getAttribute('href')).toBe('/fund/interviews');
  expect(screen.getByText('19 – 25 октября')).toBeTruthy();
  expect(screen.getByText('МСК')).toBeTruthy();
  expect(screen.getByText('Свободно').tagName).toBe('SPAN');
  expect(screen.queryByRole('button',{name:/ср, 21 октября, 15:30/})).toBeNull();
  expect(screen.queryByRole('button',{name:'Эта неделя'})).toBeNull();
  expect((screen.getByRole('button',{name:'Предыдущая неделя'}) as HTMLButtonElement).disabled).toBe(true);
 });

 it('opens a weekly slot by default and a one-off slot with the repeat switch off',async()=>{
  mocks.windows=[{id:'w',version:1,active:true,venue:'Онлайн, Телемост',join_url:'https://telemost.example/x',recurrence:'once',local_start_date:'2026-10-20',start_minute:600,end_minute:630,timezone:'Europe/Moscow'}];
  const user=userEvent.setup();view();
  await user.click(cell('пт, 23 октября, 10:00, открыть время'));
  expect(mocks.run).toHaveBeenLastCalledWith({path:'/coord/interview-availability',body:expect.objectContaining({local_start_date:'2026-10-23',start_minute:600,end_minute:630,recurrence:'weekly',weekdays:[4],duration_minutes:30,buffer_after_minutes:0,timezone:'Europe/Moscow',venue:'Онлайн, Телемост',join_url:'https://telemost.example/x'})});
  await user.click(screen.getByRole('switch',{name:'Повторять каждую неделю'}));
  await user.click(cell('пт, 23 октября, 10:30, открыть время'));
  expect(mocks.run).toHaveBeenLastCalledWith({path:'/coord/interview-availability',body:expect.objectContaining({local_start_date:'2026-10-23',start_minute:630,end_minute:660,recurrence:'once',weekdays:[]})});
 });

 it('closes a weekly date with a skip and a one-off window with a pause, and restores a skipped date',async()=>{
  mocks.slots=[slot('2026-10-23','12:30',{recurrence:'weekly',series_id:'weekly'}),slot('2026-10-23','15:00',{series_id:'once'}),slot('2026-10-23','16:00',{state:'skipped',recurrence:'weekly',series_id:'skipped'})];
  const user=userEvent.setup();view();
  await user.click(cell('пт, 23 октября, 12:30, свободно, убрать'));
  expect(mocks.run).toHaveBeenLastCalledWith({path:'/coord/interview-availability/weekly/exceptions',body:{expected_version:2,origin_date:'2026-10-23',kind:'skip'}});
  await user.click(cell('пт, 23 октября, 15:00, свободно, убрать'));
  expect(mocks.run).toHaveBeenLastCalledWith({path:'/coord/interview-availability/once/pause',body:{expected_version:2,active:false}});
  await user.click(cell('пт, 23 октября, 16:00, открыть время'));
  expect(mocks.run).toHaveBeenLastCalledWith({path:'/coord/interview-availability/skipped/exceptions',body:{expected_version:2,origin_date:'2026-10-23',kind:'restore'}});
 });

 it('shows a booked slot by the candidate short name and links to the interview',async()=>{
  mocks.slots=[slot('2026-10-23','14:00',{state:'booked',booking_id:'b1',candidate_name:'Вера Новикова'})];
  const user=userEvent.setup();view();
  await user.click(cell('пт, 23 октября, 14:00, занято: Вера Новикова'));
  expect(screen.getByText('Вера Н.')).toBeTruthy();
  expect(screen.getByText('пт, 23 октября, 14:00')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Открыть собеседование'}).getAttribute('href')).toBe('/fund/interviews?booking=b1');
 });

 it('copies free one-off slots to the next week once and moves there',async()=>{
  mocks.slots=[slot('2026-10-21','11:00'),slot('2026-10-23','15:00'),slot('2026-10-23','16:00'),slot('2026-10-30','16:00')];
  const user=userEvent.setup();view();
  await user.click(screen.getByRole('button',{name:'Скопировать на следующую'}));
  await waitFor(()=>expect(screen.getByText('Скопировали 2 слота')).toBeTruthy());
  expect(mocks.run).toHaveBeenCalledTimes(2);
  expect(mocks.run.mock.calls.map(([c])=>[c.body.local_start_date,c.body.start_minute])).toEqual([['2026-10-28',660],['2026-10-30',900]]);
  expect(screen.getByText('26 октября – 1 ноября')).toBeTruthy();
  expect(screen.getByRole('button',{name:'Эта неделя'})).toBeTruthy();
 });
});

describe('closing one slot of a longer window',()=>{
 const long=(at:string)=>slot('2026-10-23',at,{series_id:'w',recurrence:'weekly',window_start_minute:600,window_end_minute:720,buffer_after_minutes:10});
 it('narrows the day from either edge',()=>{
  expect(closeSlot(long('10:00'))).toEqual([{path:'/coord/interview-availability/w/exceptions',body:{expected_version:2,origin_date:'2026-10-23',kind:'override',start_minute:640,end_minute:720}}]);
  expect(closeSlot(long('11:20'))).toEqual([{path:'/coord/interview-availability/w/exceptions',body:{expected_version:2,origin_date:'2026-10-23',kind:'override',start_minute:600,end_minute:680}}]);
 });
 it('splits the day around a middle slot',()=>{
  const [narrow,rest]=closeSlot(long('10:40'));
  expect(narrow.body).toEqual({expected_version:2,origin_date:'2026-10-23',kind:'override',start_minute:600,end_minute:640});
  expect(rest).toEqual({path:'/coord/interview-availability',body:expect.objectContaining({local_start_date:'2026-10-23',start_minute:680,end_minute:720,recurrence:'once',duration_minutes:30,buffer_after_minutes:10})});
 });
});
