// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Link,MemoryRouter,Route,Routes} from 'react-router-dom';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '../../api/queryClient';
import {ApiError} from '../../api/transport';
import {ToastProvider} from '../../ui';
import {FirstShiftPage} from './FirstShiftPage';
import {ReflectionPage} from './ReflectionPage';
import {SignalsPage} from './SignalsPage';
const mocks=vi.hoisted(()=>({latestAudio:vi.fn(),preparation:vi.fn(),reflection:vi.fn(),reflections:vi.fn(),staffReflection:vi.fn(),staff:vi.fn(),signals:vi.fn(),privateNotes:vi.fn(),command:vi.fn(),hours:vi.fn(),profile:vi.fn(),assignment:vi.fn(),day:vi.fn()}));
vi.mock('./api',async(importOriginal)=>({...await importOriginal<typeof import('./api')>(),readLatestAudio:mocks.latestAudio,readPreparation:mocks.preparation,readReflection:mocks.reflection,readReflections:mocks.reflections,readStaffReflection:mocks.staffReflection,readStaff:mocks.staff,readSignals:mocks.signals,readPrivateNotes:mocks.privateNotes,command:mocks.command}));
vi.mock('./volunteerApi',async(importOriginal)=>({...await importOriginal<typeof import('./volunteerApi')>(),useOwnHours:()=>({data:mocks.hours()}),useOwnProfile:()=>({data:mocks.profile()}),useOwnAssignment:()=>({data:mocks.assignment()}),useOwnDay:(day:string|null)=>({data:day?mocks.day(day):undefined})}));
const initialReflection={id:null,assignment_id:'assignment',title:'Творческое занятие',version:0,mood:null,text:'',unexpected:'',help:'later',help_text:'',continuation:'discuss',restricted:false,submitted_at:null,can_submit:true,follow_up_registered:false,review:null,voice_available:false,voice_unavailable_reason:'Голосовой ввод пока недоступен. Можно написать текст.'};
const newcomer={confirmed_assignments:0,entries:[]};
const prep={assignment_id:'assignment',assignment_version:3,status:'confirmed',title:'Арт-суббота',starts_at:'2028-01-03T10:00:00Z',ends_at:'2028-01-03T14:00:00Z',timezone:'Europe/Moscow',location:'Мастерская',role_title:'Ассистент педагога',tasks:'Подготовить материалы\nПомогать ребятам',contacts:[{display_name:'Юлия Смирнова',role:'Ведущий'},{display_name:'Алевтина Кузнецова',role:'Координатор'}],checklist_version:1,version:0,checklist:[{key:'group',title:'Познакомиться с участниками группы',checked:false,href:'/me/group?assignment_id=assignment'}],questions:[],group_briefing_available:true,allowed_actions:['cancel']};
function page(path:string){return <MemoryRouter initialEntries={[path]}><QueryClientProvider client={queryClient}><ToastProvider><Routes><Route path="/my/assignments/:id/preparation" element={<FirstShiftPage/>}/><Route path="/my/assignments/:id/reflection" element={<ReflectionPage/>}/><Route path="/fund/signals" element={<SignalsPage/>}/></Routes></ToastProvider></QueryClientProvider></MemoryRouter>;}
beforeEach(()=>{queryClient.clear();for(const mock of Object.values(mocks))mock.mockReset();mocks.latestAudio.mockResolvedValue(null);mocks.hours.mockReturnValue(newcomer);mocks.profile.mockReturnValue({display_name:'Анна Петрова'});mocks.assignment.mockReturnValue(undefined);mocks.day.mockReturnValue([]);mocks.preparation.mockResolvedValue(prep);});
afterEach(()=>{cleanup();queryClient.clear();vi.unstubAllGlobals();});
describe('preparation before the first exit',()=>{
 it('greets by first name, shows who meets you and the route, and lists the role tasks',async()=>{
  render(page('/my/assignments/assignment/preparation'));
  expect(await screen.findByRole('heading',{level:1,name:'Анна, тебя ждут'})).toBeTruthy();
  expect(screen.getByText('Твой первый выход')).toBeTruthy();
  expect(screen.getByText('Арт-суббота, Мастерская. До 17:00.')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Познакомиться с группой'}).getAttribute('href')).toBe('/me/group?assignment_id=assignment');
  expect(screen.getByRole('link',{name:'Мои занятия'}).getAttribute('href')).toBe('/my/schedule');
  // One person meets the volunteer: the group leader, not every contact of the group
  expect(screen.getByText('Юлия Смирнова')).toBeTruthy();expect(screen.getByText('Ведущий')).toBeTruthy();expect(screen.queryByText('Алевтина Кузнецова')).toBeNull();
  expect(screen.getByText('Помогать ребятам')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Маршрут'}).getAttribute('href')).toBe('https://yandex.ru/maps/?text=%D0%9C%D0%B0%D1%81%D1%82%D0%B5%D1%80%D1%81%D0%BA%D0%B0%D1%8F');
  expect(screen.getByRole('link',{name:/После занятия расскажи/}).getAttribute('href')).toBe('/my/assignments/assignment/reflection');
 });
 it('calls the next занятие «Ближайшее занятие» once one is already counted',async()=>{
  mocks.hours.mockReturnValue({confirmed_assignments:2,entries:[]});mocks.profile.mockReturnValue(undefined);
  render(page('/my/assignments/assignment/preparation'));
  expect(await screen.findByRole('heading',{level:1,name:'Тебя ждут'})).toBeTruthy();
  expect(screen.getByText('Ближайшее занятие')).toBeTruthy();
 });
 it('changes checklist progress only after the actual command succeeds and handles a conflict',async()=>{
  const user=userEvent.setup();
  mocks.command.mockRejectedValueOnce(new ApiError(409,'version_conflict','Памятка уже изменилась.')).mockResolvedValueOnce({...prep,version:1,checklist:[{...prep.checklist[0],checked:true}]});
  render(page('/my/assignments/assignment/preparation'));const box=await screen.findByRole('button',{name:'Познакомиться с участниками группы'});await user.click(box);await screen.findByText('Памятка уже изменилась.');expect(box.getAttribute('aria-pressed')).toBe('false');expect(screen.getByText('0 из 1')).toBeTruthy();await user.click(box);await screen.findByText('1 из 1');expect(box.getAttribute('aria-pressed')).toBe('true');
  expect(mocks.command).toHaveBeenCalledWith('/me/assignments/assignment/checklist',{expected_version:0,checklist_version:1,checked_keys:['group']},'PUT');
 });
 it('locks the checklist and answers an invitation with «Я приду»',async()=>{
  const user=userEvent.setup();mocks.preparation.mockResolvedValue({...prep,status:'invited',contacts:[],group_briefing_available:false,allowed_actions:['confirm','decline'],checklist:prep.checklist.map(item=>({...item,href:null}))});mocks.command.mockResolvedValue({});
  render(page('/my/assignments/assignment/preparation'));
  const box=await screen.findByRole('button',{name:'Познакомиться с участниками группы'});
  expect(box.getAttribute('aria-disabled')).toBe('true');expect(screen.getByText('Отметить пункты можно после ответа «Я приду».')).toBeTruthy();
  await user.click(box);expect(mocks.command).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Я приду'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/assignments/assignment/confirm',{expected_version:3}));
 });
 it('asks inline before telling the coordinator you cannot come',async()=>{
  const user=userEvent.setup();mocks.command.mockResolvedValue({});
  render(page('/my/assignments/assignment/preparation'));
  await user.click(await screen.findByRole('button',{name:'Не смогу прийти'}));
  const note=screen.getByRole('group',{name:'Отказ от занятия'});expect(within(note).getByText('Предупредить координатора, что не сможешь?')).toBeTruthy();
  await user.click(within(note).getByRole('button',{name:'Я приду'}));expect(screen.queryByRole('group',{name:'Отказ от занятия'})).toBeNull();expect(mocks.command).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Не смогу прийти'}));await user.click(screen.getByRole('button',{name:'Да, не смогу'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/assignments/assignment/cancel',{expected_version:3}));
 });
 it('offers another date after a cancellation and sends the question as an alternate-date request',async()=>{
  const user=userEvent.setup();mocks.preparation.mockResolvedValue({...prep,status:'cancelled',contacts:[],group_briefing_available:false,allowed_actions:[]});mocks.command.mockResolvedValue({});
  render(page('/my/assignments/assignment/preparation'));
  expect(await screen.findByRole('heading',{name:'Подберём другую дату'})).toBeTruthy();
  expect(screen.getByRole('link',{name:'Написать координатору'}).getAttribute('href')).toBe('/messages');
  expect(screen.queryByRole('heading',{name:'Перед выходом'})).toBeNull();
  await user.type(screen.getByLabelText('Вопрос координатору'),'Можно в следующую субботу?');await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/me/assignments/assignment/questions',{kind:'alternate_date',text:'Можно в следующую субботу?',restricted:false}));
 });
});
describe('reflection after the занятие',()=>{
 it('keeps the saved reflection draft editable when restricted escalation has no configured specialist',async()=>{
  const user=userEvent.setup();mocks.reflection.mockResolvedValue(initialReflection);
  mocks.command.mockImplementation(async(path:string,body:Record<string,unknown>,method:string)=>{if(method==='PUT')return {...initialReflection,...body,id:'reflection',version:1};throw new ApiError(503,'support_team_unconfigured','Специалист пока не назначен. Черновик сохранён.');});
  render(page('/my/assignments/assignment/reflection'));await user.type(await screen.findByLabelText('Расскажи своими словами'),'Нужна поддержка после занятия');
  expect(screen.getByRole('button',{name:'После первого выхода'}).getAttribute('aria-expanded')).toBe('true');
  await user.click(screen.getByRole('button',{name:'Хочу поговорить'}));await user.click(screen.getByRole('checkbox',{name:/Личный или тревожный вопрос/}));await user.click(screen.getByRole('button',{name:'Отправить'}));
  await screen.findByText('Специалист пока не назначен. Черновик сохранён.');
  expect((screen.getByLabelText('Расскажи своими словами') as HTMLTextAreaElement).value).toBe('Нужна поддержка после занятия');
  expect(screen.queryByRole('button',{name:/Сказать голосом/})).toBeNull();
  expect(screen.queryByText('Так бывает у многих')).toBeNull();
  expect(mocks.command).toHaveBeenCalledWith('/me/assignments/assignment/reflection',expect.objectContaining({text:'Нужна поддержка после занятия',help:'yes',restricted:true}),'PUT');
  expect(mocks.command).toHaveBeenLastCalledWith('/me/assignments/assignment/reflection/submit',{expected_version:1});
 });
 it('saves the draft by itself a moment after the last change',async()=>{
  const user=userEvent.setup();mocks.reflection.mockResolvedValue(initialReflection);mocks.command.mockImplementation(async(_path:string,body:Record<string,unknown>)=>({...initialReflection,...body,id:'reflection',version:1}));
  render(page('/my/assignments/assignment/reflection'));
  await user.click(await screen.findByRole('button',{name:'Хорошо'}));expect(screen.getByRole('button',{name:'Хорошо'}).getAttribute('aria-pressed')).toBe('true');
  await user.click(screen.getByRole('button',{name:'Да, в этой группе'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/me/assignments/assignment/reflection',expect.objectContaining({expected_version:0,mood:'good',continuation:'yes'}),'PUT'),{timeout:4000});
  expect(mocks.command).toHaveBeenCalledTimes(1);
 });
 it('does not send an empty reflection',async()=>{
  const user=userEvent.setup();mocks.reflection.mockResolvedValue(initialReflection);
  render(page('/my/assignments/assignment/reflection'));
  await user.click(await screen.findByRole('button',{name:'Отправить'}));
  expect(screen.getByText('Выбери настроение или напиши пару слов.')).toBeTruthy();expect(mocks.command).not.toHaveBeenCalled();
 });
 it('folds the extra questions away after later занятия and shows the voice option when it is available',async()=>{
  const user=userEvent.setup();mocks.hours.mockReturnValue({confirmed_assignments:3,entries:[]});mocks.reflection.mockResolvedValue({...initialReflection,voice_available:true});
  render(page('/my/assignments/assignment/reflection'));
  const toggle=await screen.findByRole('button',{name:'Подробнее о занятии'});expect(toggle.getAttribute('aria-expanded')).toBe('false');expect(screen.queryByLabelText('Что оказалось неожиданным?')).toBeNull();
  await user.click(toggle);expect(screen.getByLabelText('Что оказалось неожиданным?')).toBeTruthy();
  const voice=screen.getByRole('button',{name:'Сказать голосом'});expect(voice.getAttribute('aria-expanded')).toBe('false');
  await user.click(voice);expect(screen.getByRole('region',{name:'Голосовая заметка'})).toBeTruthy();
 });
 it('thanks with the hours and points the занятие will bring and shows the coordinator review',async()=>{
  mocks.reflection.mockResolvedValue({...initialReflection,id:'reflection',version:2,mood:'good',submitted_at:'2028-01-03T15:00:00Z',can_submit:false,review:{id:'review',revision:1,decision:'next_date',public_message:'Ребята тебя запомнили.',next_date:'2028-01-10',assigned_staff_name:'Алевтина Кузнецова',created_at:'2028-01-03T16:10:00Z'}});
  mocks.assignment.mockReturnValue({starts_at:'2028-01-03T10:00:00Z',ends_at:'2028-01-03T14:00:00Z',timezone:'Europe/Moscow',points_multiplier:1,attendance:null});
  render(page('/my/assignments/assignment/reflection'));
  expect(await screen.findByRole('heading',{level:1,name:'Спасибо, Анна!'})).toBeTruthy();
  expect(screen.getByText('Творческое занятие, 3 января')).toBeTruthy();
  expect(await screen.findByText('4 часа и 40 баллов засчитаем, когда Юлия отметит занятие.')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Мой путь'}).getAttribute('href')).toBe('/hours');
  expect(screen.getByText('Ребята тебя запомнили.')).toBeTruthy();expect(screen.getByText('Алевтина')).toBeTruthy();
  // No own занятие on the suggested day yet: the card names the same занятие and the date
  expect(mocks.day).toHaveBeenCalledWith('2028-01-10');
  expect(screen.getByRole('heading',{name:'Творческое занятие, 10 января'})).toBeTruthy();expect(screen.getByRole('link',{name:'Обсудить'}).getAttribute('href')).toBe('/messages');expect(screen.queryByRole('button',{name:'Я приду'})).toBeNull();
  expect(screen.queryByRole('heading',{name:'Что может помочь'})).toBeNull();
 });
 it('answers a hard занятие calmly and offers support instead of the result',async()=>{
  mocks.reflection.mockResolvedValue({...initialReflection,id:'reflection',version:2,mood:'awful',submitted_at:'2028-01-03T15:00:00Z',can_submit:false,follow_up_registered:true});
  render(page('/my/assignments/assignment/reflection'));
  expect(await screen.findByRole('heading',{level:1,name:'Так бывает у многих'})).toBeTruthy();
  expect(await screen.findByText('Алевтина скоро напишет тебе. Часы засчитаем как обычно.')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Записаться'}).getAttribute('href')).toBe('/webinars');
  expect(screen.getByRole('link',{name:'Поставить паузу'}).getAttribute('href')).toBe('/profile?tab=pause');
  expect(screen.queryByRole('link',{name:'Мой путь'})).toBeNull();
 });
});
describe('reflection results and the phone layout',()=>{
 const sent={...initialReflection,id:'reflection',version:2,mood:'good',submitted_at:'2028-01-03T15:00:00Z',can_submit:false,review:{id:'review',revision:1,decision:'next_date',public_message:'Приходи ещё.',next_date:'2028-01-10',assigned_staff_name:'Алевтина Кузнецова',created_at:'2028-01-03T16:10:00Z'}};
 it('thanks with the minutes and points really counted and answers the suggested занятие right there',async()=>{
  const user=userEvent.setup();mocks.reflection.mockResolvedValue(sent);mocks.command.mockResolvedValue({});
  // The ledger has 3 hours for this занятие (after a correction), the attendance record still says 4: the ledger wins
  mocks.hours.mockReturnValue({confirmed_assignments:1,entries:[{assignment_id:'assignment',delta_minutes:240},{assignment_id:'assignment',delta_minutes:-60},{assignment_id:'other',delta_minutes:120}]});
  mocks.assignment.mockReturnValue({starts_at:'2028-01-03T10:00:00Z',ends_at:'2028-01-03T14:00:00Z',timezone:'Europe/Moscow',points_multiplier:1.5,attendance:{outcome:'attended',minutes:240}});
  mocks.day.mockReturnValue([{id:'next',version:2,status:'invited',allowed_actions:['confirm','decline'],title:'Арт-суббота',starts_at:'2028-01-10T11:00:00Z',timezone:'Europe/Moscow'}]);
  render(page('/my/assignments/assignment/reflection'));
  expect(await screen.findByText('Засчитали 3 часа и 45 баллов.')).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Арт-суббота, 14:00'})).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Я приду'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/assignments/next/confirm',{expected_version:2}));
  expect(screen.getByRole('link',{name:'Обсудить'}).getAttribute('href')).toBe('/messages');
 });
 it('leads a confirmed suggested занятие to its preparation',async()=>{
  mocks.reflection.mockResolvedValue(sent);
  mocks.day.mockReturnValue([{id:'next',version:3,status:'confirmed',allowed_actions:['cancel'],title:'Арт-суббота',starts_at:'2028-01-10T11:00:00Z',timezone:'Europe/Moscow'}]);
  render(page('/my/assignments/assignment/reflection'));
  expect((await screen.findByRole('link',{name:'Подготовиться'})).getAttribute('href')).toBe('/my/assignments/next/preparation');
  expect(screen.queryByRole('button',{name:'Я приду'})).toBeNull();
 });
 it('asks for a voice note first on a phone and still lets you type',async()=>{
  const user=userEvent.setup();
  vi.stubGlobal('matchMedia',(query:string)=>({matches:query.includes('max-width'),media:query,addEventListener:()=>{},removeEventListener:()=>{}}));
  mocks.reflection.mockResolvedValue({...initialReflection,voice_available:true});mocks.command.mockImplementation(async(_path:string,body:Record<string,unknown>)=>({...initialReflection,...body,id:'reflection',version:1}));
  render(page('/my/assignments/assignment/reflection'));
  expect(await screen.findByRole('heading',{level:1,name:'Как прошло занятие?'})).toBeTruthy();
  // The extra first-exit questions start folded on a phone
  expect(screen.getByRole('button',{name:'После первого выхода'}).getAttribute('aria-expanded')).toBe('false');
  const mic=screen.getByRole('button',{name:'Расскажи голосом'});expect(screen.queryByLabelText('Расскажи своими словами')).toBeNull();
  await user.click(mic);expect(mic.getAttribute('aria-expanded')).toBe('true');expect(screen.getByRole('region',{name:'Голосовая заметка'})).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Написать текстом'}));
  await user.type(screen.getByLabelText('Расскажи своими словами'),'Было спокойно');
  await user.click(screen.getByRole('button',{name:'Отправить'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenLastCalledWith('/me/assignments/assignment/reflection/submit',{expected_version:1}));
 });
});
describe('staff follow-up',()=>{
 it('shows staff review controls from server capabilities and sends only a public pause decision',async()=>{
  const user=userEvent.setup();const row={...initialReflection,id:'reflection',group_id:null,user_id:'volunteer',display_name:'Волонтёр',version:2,submitted_at:'2028-01-03T12:00:00Z',can_submit:false,text:'Хочу обсудить продолжение',signal_id:'signal',can_review:true,private_notes_available:false};
  mocks.reflections.mockResolvedValue({items:[row]});mocks.staffReflection.mockResolvedValue(row);mocks.staff.mockResolvedValue({items:[{id:'coordinator',display_name:'Координатор',restricted_eligible:false}]});mocks.command.mockResolvedValue(row);
  render(page('/fund/signals?reflection_id=reflection'));await screen.findByRole('heading',{name:'Следующий шаг'});expect(screen.queryByLabelText('Внутренняя заметка')).toBeNull();expect(mocks.privateNotes).not.toHaveBeenCalled();
  await user.click(screen.getByRole('combobox',{name:'Решение после выхода'}));await user.click(screen.getByRole('option',{name:'Пауза'}));await user.type(screen.getByLabelText('Договорённость для волонтёра'),'Договорились о паузе.');await user.click(screen.getByRole('combobox',{name:'Ответственный за следующий шаг'}));await user.click(screen.getByRole('option',{name:'Координатор'}));await user.click(screen.getByRole('button',{name:'Сохранить следующий шаг'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('/coord/reflections/reflection/review',{expected_version:2,decision:'pause',public_message:'Договорились о паузе.',assigned_user_id:'coordinator',next_date:null,internal_note:''}));
 });
});

it('does not carry a private question into another assignment preparation page',async()=>{
 mocks.preparation.mockImplementation(async(id)=>({...prep,assignment_id:id,title:'Занятие '+id}));
 render(<MemoryRouter initialEntries={['/my/assignments/one/preparation']}><QueryClientProvider client={queryClient}><ToastProvider><Link to="/my/assignments/two/preparation">Другое занятие</Link><Routes><Route path="/my/assignments/:id/preparation" element={<FirstShiftPage/>}/></Routes></ToastProvider></QueryClientProvider></MemoryRouter>);
 fireEvent.change(await screen.findByLabelText('Вопрос координатору'),{target:{value:'Личный вопрос к первому занятию'}});fireEvent.click(screen.getByRole('checkbox',{name:/Личный вопрос/}));fireEvent.click(screen.getByRole('link',{name:'Другое занятие'}));await screen.findByText(/Занятие two, Мастерская/);expect((screen.getByLabelText('Вопрос координатору') as HTMLTextAreaElement).value).toBe('');expect((screen.getByRole('checkbox',{name:/Личный вопрос/}) as HTMLInputElement).checked).toBe(false);
});
