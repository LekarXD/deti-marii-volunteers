// @vitest-environment jsdom
import React from 'react';
import {afterEach, beforeEach, describe, expect, it, vi, type MockInstance} from 'vitest';
import {cleanup, render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import * as transport from '../../api/transport';
import type {components} from '../../api/generated/schema';
import type {AssignmentParticipation} from '../activities/participationApi';
import type {Preparation, Assignment} from '../learning/api';
import {HomePage} from './HomePage';
import {assignmentWhen, homeScheduleRange, learningDestination, upcomingAssignments} from './model';

const now = Date.parse('2026-10-21T22:00:00Z');
const assignment = (changes: Partial<AssignmentParticipation> = {}): AssignmentParticipation => ({
  id:'first', user_id:'volunteer', display_name:'Тестовый волонтёр', occurrence_id:'event', staffing_need_id:'need',
  occurrence_status:'scheduled', title:'Мастерская', role_title:'Помощь на занятии', status:'confirmed', origin:'invitation', approved_at:null, confirmed_at:null,
  starts_at:'2026-10-22T09:00:00Z', ends_at:'2026-10-22T11:00:00Z', timezone:'Europe/Moscow', location:'Мастерская фонда',
  readiness:[], history:[], allowed_actions:[], conditions_version:1, points_multiplier:1, approval_required:false, version:1, ...changes,
});
const track: Assignment = {id:'learning', track_id:'track', track_key:'intro', release_id:'release', release_number:1, change_note:'',
  title:'Подготовка к занятию', intro:'Полезные материалы', acknowledged:false, completed:false,
  assessment_version_id:null, latest_attempt_id:null, latest_attempt_state:null, reacknowledgement_required:false,
  lessons:[{id:'read',key:'read',lesson_id:'read-source',minutes:5,mode:'feed',title:'Знакомство',completed:true},{id:'next',key:'next',lesson_id:'next-source',minutes:10,mode:'feed',title:'На занятии',completed:false}]};
const learning: Preparation = {assignments:[track], introduction_completed:false, booking_requires_introduction:false};
const preparation: components['schemas']['AssignmentPreparationView'] = {
  assignment_id:'first', assignment_version:1, title:'Мастерская', status:'confirmed', starts_at:'2026-10-22T09:00:00Z', ends_at:'2026-10-22T11:00:00Z',
  timezone:'Europe/Moscow', location:'Вход со двора', role_title:'Помощник', tasks:'Помочь разложить материалы', group_briefing_available:true,
  contacts:[{role:'Ведущий занятия',display_name:'Тестовый ведущий'}],
  checklist:[{key:'read',title:'Прочитать памятку',checked:true},{key:'bring',title:'Взять сменную обувь',checked:false}],
  checklist_version:1, questions:[], allowed_actions:[], version:1,
};
const eventCard = (title: string, changes: Partial<components['schemas']['VolunteerEventCard']> = {}): components['schemas']['VolunteerEventCard'] => ({
  occurrence_id:title, series_id:'series', title, program:'Творческие мастерские', kind:'activity', format:'onsite', location:'Мастерская фонда', audience:'',
  status:'scheduled', starts_at:'2026-10-24T11:00:00Z', ends_at:'2026-10-24T13:00:00Z', timezone:'Europe/Moscow', best_need_id:'need', reasons:[], full:false, conflict:false,
  needs:[{id:'need', version:1, role_id:'role', role_title:'Ассистент педагога', task:'', required:4, confirmed:2, missing:2, approval_policy:'self_confirmation', preparation_requirements:[], allowed_actions:['sign-up']}], ...changes,
});
let feed: components['schemas']['VolunteerEventFeed'];
const blankHours: components['schemas']['HoursView'] = {total_minutes:0, confirmed_assignments:0, pending_minutes:0, ledger_pending:0, entries:[], manual_requests:[], achievements:[], gratitudes:[],
  level:{key:null, title:null, next_title:'Первые шаги', next_minutes:null, letter_hint:false, steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:false,current:false},{key:'team',title:'В команде',minutes:1200,reached:false,current:false},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]}, points:{balance:0, earned:0, reserved:0, spent:0, can_request:false, history:[]}};
let hours: components['schemas']['HoursView'];
let rows: AssignmentParticipation[];
let nextRows: AssignmentParticipation[] | undefined;
let learningError: Error | undefined;
let assignmentsError: Error | undefined;
let nextPageError: Error | undefined;
let apiSpy: MockInstance<typeof transport.api>;
const clients: QueryClient[] = [];
beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(now);
  rows = []; hours = blankHours; nextRows = undefined; learningError = undefined; assignmentsError = undefined; nextPageError = undefined;
  feed = {algorithm_version:'rules-v3', can_sign_up:true, items:[]};
  apiSpy = vi.spyOn(transport, 'api').mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.startsWith('/me/events?')) return feed as T;
    if(path.startsWith('/me/schedule?')) {
      if (assignmentsError) throw assignmentsError;
      if (path.includes('cursor=next') && nextPageError) throw nextPageError;
      return (path.includes('cursor=next') ? {items:nextRows ?? [],next_cursor:null} : {items:rows,next_cursor:nextRows ? 'next' : null}) as T;
    }
    if (path === '/api/v1/me/preparation') {if(learningError) throw learningError; return learning as T;}
    if (path === '/me/assignments/first/preparation') return preparation as T;
    if (path === '/me/hours') return hours as T;
    throw new Error(`Unexpected home API: ${path}`);
  });
});
afterEach(() => {cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks();});
function view() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);
  return render(<QueryClientProvider client={client}><MemoryRouter><HomePage/></MemoryRouter></QueryClientProvider>);
}
describe('home projection', () => {
  it('chooses active invitations and confirmed events by actual start time, excluding history and cancelled items', () => {
    const values = [assignment({id:'later',starts_at:'2026-10-23T09:00:00Z'}),assignment({id:'cancelled',status:'cancelled'}),
      assignment({id:'event-cancelled',occurrence_status:'cancelled'}),assignment({id:'event-postponed',occurrence_status:'postponed'}),
      assignment({id:'attended',attendance:{id:'attendance',version:1,outcome:'attended',minutes:60,ledger_state:'recorded'}}),
      assignment({id:'expired',ends_at:'2026-10-20T11:00:00Z'}),assignment({id:'invitation',status:'invited',starts_at:'2026-10-22T08:00:00Z'}),
      assignment({id:'ongoing',starts_at:'2026-10-21T21:00:00Z',ends_at:'2026-10-21T23:00:00Z'}),assignment({id:'invalid',starts_at:'not a date'})];
    expect(upcomingAssignments(values, now).map(item=>item.id)).toEqual(['ongoing','invitation','later']);
    expect(values[0].id).toBe('later');
  });
  it('labels today in the event timezone rather than the browser date, and does not invent a learning lesson', () => {
    const value = assignmentWhen(assignment(), now);
    expect(value).toEqual({today:true,date:'Сегодня',time:'12:00–14:00'});
    expect(homeScheduleRange(now)).toEqual({from:'2026-10-22',to:'2027-01-19'});
    expect(learningDestination({...track,lessons:[]})).toBe('/academy');
    expect(learningDestination({...track,lessons:[],assessment_version_id:'assessment'})).toBe('/academy/lessons/assessment?assignment=learning');
  });
});
describe('volunteer home', () => {
  it('loads all assignment pages before choosing the nearest hero and uses the existing preparation/learning APIs', async () => {
    rows=[assignment({id:'later',title:'Позже',starts_at:'2026-10-23T09:00:00Z',ends_at:'2026-10-23T11:00:00Z'})];nextRows=[assignment()];
    view();
    await userEvent.setup().click(await screen.findByRole('button',{name:'Загрузить ещё занятия'}));
    await screen.findByRole('heading',{name:/Сегодня 12:00–14:00/});
    expect(screen.getByRole('link',{name:'Подготовиться к выходу'}).getAttribute('href')).toBe('/my/assignments/first/preparation');
    await screen.findByText('Тестовый ведущий');
    expect(screen.getByText('Вход со двора')).toBeTruthy();
    expect(screen.getByText('Перед выходом: 1 из 2 пунктов выполнено')).toBeTruthy();
    expect(screen.getByText('Взять сменную обувь')).toBeTruthy();
    const progress=screen.getByRole('progressbar',{name:'Пройдено уроков'}) as HTMLProgressElement;
    expect([progress.value,progress.max]).toEqual([1,2]);
    expect(screen.getByRole('link',{name:'Продолжить обучение'}).getAttribute('href')).toBe('/academy/lessons/next?assignment=learning');
    expect(apiSpy.mock.calls.some(call=>String(call[0]).includes('cursor=next'))).toBe(true);
    expect(apiSpy.mock.calls.filter(call=>String(call[0]).startsWith('/me/schedule?')).every(call=>String(call[0]).includes('from=2026-10-22&to=2027-01-19&timezone=Europe/Moscow&state=active'))).toBe(true);
    expect(apiSpy.mock.calls.some(call=>String(call[0]).startsWith('/me/assignments?'))).toBe(false);
    expect(apiSpy.mock.calls.every(call=>!call[1] || !call[1].method || call[1].method==='GET')).toBe(true);
  });
  it('keeps invitations actionable through existing participation controls and does not expose unconfirmed preparation', async () => {
    rows=[assignment({status:'invited'})];view();
    const invitations=await screen.findByRole('region',{name:'Тебя приглашают'});
    expect(within(invitations).getByRole('link',{name:/Ответить на приглашение/}).getAttribute('href')).toBe('/my/assignments/first');
    expect(screen.queryByText('Участие подтверждено')).toBeNull();
    expect(apiSpy.mock.calls.some(call=>String(call[0]).includes('/first/preparation'))).toBe(false);
    expect(screen.queryByRole('button',{name:/приду/})).toBeNull();
  });
  it('shows the genuine newcomer path without invented identity, hours or matching scores', async () => {
    view();await screen.findByRole('heading',{name:'Впереди новые встречи'});
    expect(screen.getByRole('link',{name:'Моя анкета'}).getAttribute('href')).toBe('/application');
    expect(screen.getByRole('link',{name:'Знакомство с координатором'}).getAttribute('href')).toBe('/interviews');
    expect(screen.getByRole('link',{name:'Посмотреть возможности'}).getAttribute('href')).toBe('/opportunities');
    expect(screen.queryByText(/Анна|недель подряд|Совпадение|Подобрано для тебя/)).toBeNull();
  });
  it('shows level, hours and points from the server on the my path card', async () => {
    hours={...blankHours, total_minutes:2760, level:{key:'team', title:'В команде', next_title:'Друг фонда', next_minutes:3000, letter_hint:false, steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:true,current:false},{key:'team',title:'В команде',minutes:1200,reached:true,current:true},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]}, points:{...blankHours.points, balance:460}};
    view();const card=await screen.findByRole('link',{name:'Мой путь'});
    expect(card.getAttribute('href')).toBe('/hours');
    expect(within(card).getByRole('heading',{name:'В команде'})).toBeTruthy();expect(within(card).getByText('46 часов помощи, до «Друг фонда» 4 часа')).toBeTruthy();
    expect(within(card).getByText('460 баллов')).toBeTruthy();expect(within(card).getByText('Опора фонда')).toBeTruthy();
  });
  it('retains the confirmed assignment when learning fails and retries only the failed read', async () => {
    rows=[assignment()];learningError=new Error('Обучение временно недоступно');view();
    await screen.findByText('Обучение временно недоступно');
    expect(await screen.findByText('Участие подтверждено')).toBeTruthy();
    learningError=undefined;
    await userEvent.setup().click(screen.getByRole('button',{name:'Попробовать ещё раз'}));
    await waitFor(()=>expect(screen.queryByText('Обучение временно недоступно')).toBeNull());
    expect(screen.getByRole('link',{name:'Продолжить обучение'})).toBeTruthy();
  });
  it('does not misrepresent a failed list or missing pagination page as an empty/newcomer result', async () => {
    rows=[assignment({id:'later'})];nextRows=[assignment()];nextPageError=new Error('Приглашения временно недоступны');view();
    await screen.findByRole('heading',{name:'Расписание загружено не полностью'});
    expect(apiSpy.mock.calls.some(call=>String(call[0]).includes('cursor=next'))).toBe(false);
    await userEvent.setup().click(screen.getByRole('button',{name:'Загрузить ещё занятия'}));
    await screen.findByText('Приглашения временно недоступны');
    expect(screen.queryByRole('heading',{name:'Впереди новые встречи'})).toBeNull();
    expect(screen.queryByText('Ближайшее занятие')).toBeNull();
    nextPageError=undefined;
    await userEvent.setup().click(screen.getByRole('button',{name:'Попробовать ещё раз'}));
    expect(await screen.findByText('Участие подтверждено')).toBeTruthy();
  });
  it('shows the top three open events from the server-ranked feed, never full ones or a score', async () => {
    feed={algorithm_version:'rules-v3',can_sign_up:true,items:[eventCard('Арт-суббота'),eventCard('Выезд',{full:true}),eventCard('Шерстяной Базар'),eventCard('Экскурсия'),eventCard('Онлайн-афиша')]};
    view();
    const section=(await screen.findByRole('heading',{name:'Подобрано для тебя'})).closest('section') as HTMLElement;
    const tiles=within(section).getAllByRole('link').filter(link=>link.getAttribute('href')?.startsWith('/events/'));
    expect(tiles.map(link=>link.querySelector('.h3')?.textContent)).toEqual(['Арт-суббота','Шерстяной Базар','Экскурсия']);
    expect(tiles[0].getAttribute('href')).toBe('/events/Арт-суббота');
    expect(tiles[0].textContent).toContain('Записались 2 из 4');
    expect(within(section).getByRole('link',{name:'Все мероприятия'}).getAttribute('href')).toBe('/events');
    await userEvent.setup().click(within(section).getByRole('button',{name:'Почему так'}));
    expect(within(section).getByText('роль подходит к твоей анкете;')).toBeTruthy();
    expect(section.textContent).not.toMatch(/балл|score|%/i);
  });
  it('hides the picked events while sign-up is locked for a newcomer', async () => {
    feed={algorithm_version:'rules-v3',can_sign_up:false,locked_reason:'meeting_required',locked_message:'Записаться можно после встречи с координатором.',items:[eventCard('Арт-суббота')]};
    view();await screen.findByRole('heading',{name:'Впереди новые встречи'});
    await waitFor(()=>expect(apiSpy.mock.calls.some(call=>String(call[0]).startsWith('/me/events?'))).toBe(true));
    expect(screen.queryByText('Подобрано для тебя')).toBeNull();
  });
});
