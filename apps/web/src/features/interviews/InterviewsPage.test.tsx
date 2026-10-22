// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,useLocation} from 'react-router-dom';
import type {StaffBooking} from './api';
import {CandidateInterviewsPage,InterviewsPage} from './InterviewsPage';

const mocks=vi.hoisted(()=>({mutate:vi.fn(),bookings:[] as unknown[],slots:[] as unknown[]}));
vi.mock('./api',()=>({meetingFormat:'Онлайн-собеседование',useInterviews:()=>({data:mocks.bookings,isLoading:false}),useSlots:()=>({data:mocks.slots,isLoading:false,refetch:()=>{}}),
 useInterviewCommand:()=>({mutate:mocks.mutate,reset:()=>{},isPending:false,error:null})}));
vi.mock('../applications/api',()=>({useCandidate:()=>({isLoading:false,data:{revision:{answers:{directions:['Помощь на занятиях'],participation:'Каждую неделю',telegram:'vera_n',volExpText:'Студентка-дефектолог'}}}})}));
const booking=(id:string,name:string,starts:string,changes:Partial<StaffBooking>={}):StaffBooking=>{const start=new Date(starts);return {id,application_id:`app-${id}`,slot_id:`slot-${id}`,coordinator_id:'coord',starts_at:start.toISOString(),ends_at:new Date(start.getTime()+1800000).toISOString(),venue:'Онлайн, Яндекс Телемост',join_url:null,status:'booked',version:3,cancel_reason:null,result:null,events:[{kind:'booked',created_at:'2026-10-20T10:00:00Z'}],candidate_name:name,private_note:null,confirmed:true,...changes};};
function Where(){const l=useLocation();return <output data-testid="where">{l.search}</output>;}
const view=(path='/fund/interviews')=>render(<MemoryRouter initialEntries={[path]}><InterviewsPage/><Where/></MemoryRouter>);

beforeEach(()=>{
 vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2026-10-22T09:00:00Z'));mocks.mutate.mockReset();
 mocks.bookings=[booking('early','Тимур Давыдов','2026-10-22T10:00:00+03:00'),booking('vera','Вера Новикова','2026-10-22T14:00:00+03:00'),booking('gleb','Глеб Сорокин','2026-10-23T12:00:00+03:00',{confirmed:false}),
  booking('sergey','Сергей Миронов','2026-10-21T15:00:00+03:00',{status:'completed',result:{outcome:'Подходит',public_agreement:'x',next_contact_date:null}}),booking('gone','Отменённый Кандидат','2026-10-26T11:00:00+03:00',{status:'cancelled'})];
 mocks.slots=[{id:'s1',version:5,series_id:'w',coordinator_id:'coord',starts_at:'2026-10-26T07:00:00Z',ends_at:'2026-10-26T07:30:00Z',timezone:'Europe/Moscow',venue:'Онлайн',join_url:null}];
});
afterEach(()=>{cleanup();vi.useRealTimers();});

describe('staff interviews',()=>{
 it('groups upcoming interviews by day with one waiting word and no panel until a click',()=>{
  view();
  expect(screen.getByRole('heading',{level:1,name:'Собеседования'})).toBeTruthy();
  expect(screen.getByRole('link',{name:'Свободные слоты'}).getAttribute('href')).toBe('/fund/interviews/availability');
  expect(screen.getAllByRole('heading',{level:2}).map(h=>h.textContent)).toEqual(['Сегодня','Завтра, пятница']);
  expect(screen.getAllByText('ждём ответа')).toHaveLength(1);
  expect(screen.queryByText('Отменённый Кандидат')).toBeNull();
  expect(screen.queryByRole('complementary')).toBeNull();
  expect(document.body.textContent).not.toContain('·');
 });

 it('opens the panel from the URL and records an outcome once the interview started',async()=>{
  const user=userEvent.setup();view();
  await user.click(screen.getByRole('button',{name:/Вера Новикова/}));
  expect(screen.getByTestId('where').textContent).toBe('?booking=vera');
  let panel=screen.getByRole('complementary');
  expect(within(panel).getByText('Сегодня, 14:00–14:30')).toBeTruthy();
  expect(within(panel).getByText('Помощь на занятиях')).toBeTruthy();
  expect(within(panel).getByText('Telegram @vera_n')).toBeTruthy();
  expect(within(panel).queryByRole('button',{name:'Записать итог'})).toBeNull();
  await user.click(screen.getByRole('button',{name:/Тимур Давыдов/}));
  panel=screen.getByRole('complementary');
  await user.click(within(panel).getByRole('button',{name:'Записать итог'}));
  expect((within(panel).getByRole('button',{name:'Сохранить итог'}) as HTMLButtonElement).disabled).toBe(true);
  await user.click(within(panel).getByRole('radio',{name:'Не пришёл'}));
  await user.type(within(panel).getByRole('textbox',{name:'Заметка для команды'}),'Не отвечал');
  await user.click(within(panel).getByRole('button',{name:'Сохранить итог'}));
  expect(mocks.mutate).toHaveBeenCalledWith({path:'/interviews/early/mark-missed',body:expect.objectContaining({expected_version:3,outcome:'Не пришёл',private_note:'Не отвечал'})},expect.any(Object));
 });

 it('moves to a free slot chip and cancels after an inline confirmation',async()=>{
  mocks.mutate.mockImplementation((_:unknown,options?:{onSuccess?:()=>void})=>options?.onSuccess?.());
  const user=userEvent.setup();view('/fund/interviews?booking=gleb');
  const panel=screen.getByRole('complementary');
  await user.click(within(panel).getByRole('button',{name:'Перенести'}));
  expect(within(panel).getByText('Пн, 26 октября')).toBeTruthy();
  await user.click(within(panel).getByRole('button',{name:'10:00'}));
  await user.click(within(panel).getByRole('button',{name:'Перенести'}));
  expect(mocks.mutate).toHaveBeenLastCalledWith({path:'/interviews/gleb/reschedule',body:{slot_id:'s1',slot_version:5,expected_version:3}},expect.any(Object));
  expect(within(panel).getByText('Перенесли, кандидат получит сообщение')).toBeTruthy();
  await user.click(within(panel).getByRole('button',{name:'Отменить собеседование'}));
  await user.click(within(panel).getByRole('button',{name:'Отменить'}));
  expect(mocks.mutate).toHaveBeenLastCalledWith({path:'/interviews/gleb/cancel',body:expect.objectContaining({expected_version:3})},expect.any(Object));
  expect(screen.getByTestId('where').textContent).toBe('');
 });

 it('opens a past booking from the link on load and switches to past interviews',()=>{
  view('/fund/interviews?booking=sergey');
  expect(screen.getByRole('radio',{name:'Прошедшие'}).getAttribute('aria-checked')).toBe('true');
  expect(screen.getByRole('heading',{level:2,name:'Среда, 21 октября'})).toBeTruthy();
  expect(within(screen.getByRole('complementary')).getByRole('heading',{name:'Сергей Миронов'})).toBeTruthy();
 });

 it('shows past interviews with their outcome',async()=>{
  const user=userEvent.setup();view();
  await user.click(screen.getByRole('radio',{name:'Прошедшие'}));
  expect(screen.getByRole('heading',{level:2,name:'Среда, 21 октября'})).toBeTruthy();
  expect(screen.getByText('подходит')).toBeTruthy();
  await user.click(screen.getByRole('button',{name:/Сергей Миронов/}));
  expect(within(screen.getByRole('complementary')).getByText('Итог: подходит')).toBeTruthy();
  expect(within(screen.getByRole('complementary')).getByRole('link',{name:'Подобрать первое мероприятие'})).toBeTruthy();
 });
});

it('keeps the candidate wording for the candidate dialog',async()=>{
 mocks.bookings=[booking('mine','Я','2026-10-23T12:00:00+03:00')];
 const user=userEvent.setup();render(<MemoryRouter><CandidateInterviewsPage/></MemoryRouter>);
 await user.click(screen.getByRole('button',{name:'Открыть встречу'}));
 expect(screen.getByRole('dialog',{name:'Встреча с координатором'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Записать итог'})).toBeNull();
});
