// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Link,MemoryRouter,Route,Routes} from 'react-router-dom';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '../../api/queryClient';
import {ApiError} from '../../api/transport';
import {ToastProvider} from '../../ui';
import {FirstShiftPage} from './FirstShiftPage';
import {ReflectionPage} from './ReflectionPage';
import {SignalsPage} from './SignalsPage';
const mocks=vi.hoisted(()=>({latestAudio:vi.fn(),preparation:vi.fn(),reflection:vi.fn(),reflections:vi.fn(),staffReflection:vi.fn(),staff:vi.fn(),signals:vi.fn(),privateNotes:vi.fn(),command:vi.fn()}));
vi.mock('./api',async(importOriginal)=>({...await importOriginal<typeof import('./api')>(),readLatestAudio:mocks.latestAudio,readPreparation:mocks.preparation,readReflection:mocks.reflection,readReflections:mocks.reflections,readStaffReflection:mocks.staffReflection,readStaff:mocks.staff,readSignals:mocks.signals,readPrivateNotes:mocks.privateNotes,command:mocks.command}));
const initialReflection={id:null,assignment_id:'assignment',title:'Творческое занятие',version:0,mood:null,text:'',unexpected:'',help:'later',help_text:'',continuation:'discuss',restricted:false,submitted_at:null,can_submit:true,follow_up_registered:false,review:null,voice_available:false,voice_unavailable_reason:'Голосовой ввод пока недоступен. Можно написать текст.'};
function page(path:string){return <MemoryRouter initialEntries={[path]}><QueryClientProvider client={queryClient}><ToastProvider><Routes><Route path="/my/assignments/:id/preparation" element={<FirstShiftPage/>}/><Route path="/my/assignments/:id/reflection" element={<ReflectionPage/>}/><Route path="/fund/signals" element={<SignalsPage/>}/></Routes></ToastProvider></QueryClientProvider></MemoryRouter>;}
beforeEach(()=>{queryClient.clear();for(const mock of Object.values(mocks))mock.mockReset();mocks.latestAudio.mockResolvedValue(null);});
afterEach(()=>{cleanup();queryClient.clear();});
describe('follow-up journeys',()=>{
 it('keeps the saved reflection draft editable when restricted escalation has no configured specialist',async()=>{
  const user=userEvent.setup();mocks.reflection.mockResolvedValue(initialReflection);
  mocks.command.mockImplementation(async(path:string,body:Record<string,unknown>,method:string)=>{if(method==='PUT')return {...initialReflection,...body,id:'reflection',version:1};throw new ApiError(503,'support_team_unconfigured','Специалист пока не назначен. Черновик сохранён.');});
  render(page('/my/assignments/assignment/reflection'));await user.type(await screen.findByLabelText('Расскажи своими словами'),'Нужна поддержка после занятия');await user.click(screen.getByRole('checkbox',{name:/Личный или тревожный вопрос/}));await user.click(screen.getByRole('button',{name:'Отправить'}));
  await screen.findByText('Специалист пока не назначен. Черновик сохранён.');
  expect((screen.getByLabelText('Расскажи своими словами') as HTMLTextAreaElement).value).toBe('Нужна поддержка после занятия');
  expect(screen.getByText('Голосовой ввод пока недоступен. Можно написать текст.')).toBeTruthy();
  expect(screen.queryByText('Запрос поддержки зарегистрирован.')).toBeNull();
  expect(mocks.command).toHaveBeenNthCalledWith(2,'/me/assignments/assignment/reflection/submit',{expected_version:1});
 });
 it('changes checklist progress only after the actual command succeeds and handles a conflict',async()=>{
  const user=userEvent.setup();const prep={assignment_id:'assignment',assignment_version:3,status:'confirmed',title:'Занятие',starts_at:'2028-01-03T10:00:00Z',ends_at:'2028-01-03T11:00:00Z',timezone:'Europe/Moscow',location:'Мастерская',role_title:'Помощник',tasks:'Подготовить материалы',contacts:[],checklist_version:1,version:0,checklist:[{key:'group',title:'Познакомиться с участниками группы',checked:false,href:'/me/group?assignment_id=assignment'}],questions:[],group_briefing_available:true,allowed_actions:['cancel']};
  mocks.preparation.mockResolvedValue(prep);mocks.command.mockRejectedValueOnce(new ApiError(409,'version_conflict','Памятка уже изменилась.')).mockResolvedValueOnce({...prep,version:1,checklist:[{...prep.checklist[0],checked:true}]});
  render(page('/my/assignments/assignment/preparation'));const checkbox=await screen.findByRole('checkbox',{name:/Познакомиться/});await user.click(checkbox);await screen.findByText('Памятка уже изменилась.');expect((checkbox as HTMLInputElement).checked).toBe(false);expect(screen.getByText('0 из 1')).toBeTruthy();await user.click(checkbox);await screen.findByText('1 из 1');expect((checkbox as HTMLInputElement).checked).toBe(true);
  expect(mocks.command).toHaveBeenCalledWith('/me/assignments/assignment/checklist',{expected_version:0,checklist_version:1,checked_keys:['group']},'PUT');
 });
 it('shows staff review controls from server capabilities and sends only a public pause decision',async()=>{
  const user=userEvent.setup();const row={...initialReflection,id:'reflection',group_id:null,user_id:'volunteer',display_name:'Волонтёр',version:2,submitted_at:'2028-01-03T12:00:00Z',can_submit:false,text:'Хочу обсудить продолжение',signal_id:'signal',can_review:true,private_notes_available:false};
  mocks.reflections.mockResolvedValue({items:[row]});mocks.staffReflection.mockResolvedValue(row);mocks.staff.mockResolvedValue({items:[{id:'coordinator',display_name:'Координатор',restricted_eligible:false}]});mocks.command.mockResolvedValue(row);
  render(page('/fund/signals?reflection_id=reflection'));await screen.findByRole('heading',{name:'Следующий шаг'});expect(screen.queryByLabelText('Внутренняя заметка')).toBeNull();expect(mocks.privateNotes).not.toHaveBeenCalled();
  await user.click(screen.getByRole('combobox',{name:'Решение после выхода'}));await user.click(screen.getByRole('option',{name:'Пауза'}));await user.type(screen.getByLabelText('Договорённость для волонтёра'),'Договорились о паузе.');await user.click(screen.getByRole('combobox',{name:'Ответственный за следующий шаг'}));await user.click(screen.getByRole('option',{name:'Координатор'}));await user.click(screen.getByRole('button',{name:'Сохранить следующий шаг'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/coord/reflections/reflection/review',{expected_version:2,decision:'pause',public_message:'Договорились о паузе.',assigned_user_id:'coordinator',next_date:null,internal_note:''}));
 });
});

it('does not carry a private question into another assignment preparation page',async()=>{
 mocks.preparation.mockImplementation(async(id)=>({assignment_id:id,title:'Занятие '+id,status:'confirmed',starts_at:'2028-01-01T10:00:00Z',timezone:'Europe/Moscow',location:'Мастерская',allowed_actions:[],group_briefing_available:false,contacts:[],checklist:[],questions:[],version:1}));
 render(<MemoryRouter initialEntries={['/my/assignments/one/preparation']}><QueryClientProvider client={queryClient}><ToastProvider><Link to="/my/assignments/two/preparation">Другое занятие</Link><Routes><Route path="/my/assignments/:id/preparation" element={<FirstShiftPage/>}/></Routes></ToastProvider></QueryClientProvider></MemoryRouter>);
 fireEvent.change(await screen.findByLabelText('Вопрос координатору'),{target:{value:'Личный вопрос к первому занятию'}});fireEvent.click(screen.getByRole('checkbox',{name:/Личный вопрос/}));fireEvent.click(screen.getByRole('link',{name:'Другое занятие'}));await screen.findByText('Занятие two, Мастерская');expect((screen.getByLabelText('Вопрос координатору') as HTMLTextAreaElement).value).toBe('');expect((screen.getByRole('checkbox',{name:/Личный вопрос/}) as HTMLInputElement).checked).toBe(false);
});
