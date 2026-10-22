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
import {placesFor} from '../activities/eventsApi';
import {
  assignmentWhen, firstName, hadConfirmedPast, heroEyebrow, heroKind, homePastRange, homeScheduleRange, lateSent, learningDestination, pathLine, pickedEvents, startPath, upcomingAssignments,
} from './model';

type Schemas = components['schemas'];
const now = Date.parse('2026-10-21T22:00:00Z'); // 01:00 on Thursday 22 October in Moscow
const assignment = (changes: Partial<AssignmentParticipation> = {}): AssignmentParticipation => ({
  id:'first', user_id:'volunteer', display_name:'Тестовый волонтёр', occurrence_id:'event', staffing_need_id:'need',
  occurrence_status:'scheduled', title:'Мастерская', role_title:'Помощь на занятии', status:'confirmed', origin:'invitation', approved_at:null, confirmed_at:null,
  starts_at:'2026-10-22T09:00:00Z', ends_at:'2026-10-22T11:00:00Z', timezone:'Europe/Moscow', location:'Мастерская фонда',
  readiness:[], history:[], allowed_actions:(changes.status ?? 'confirmed') === 'invited' ? ['confirm','decline'] : ['cancel'], conditions_version:1, points_multiplier:1, approval_required:false, version:1, ...changes,
});
const tomorrow = {starts_at:'2026-10-23T09:00:00Z', ends_at:'2026-10-23T11:00:00Z'};
const track: Assignment = {id:'learning', track_id:'track', track_key:'intro', release_id:'release', release_number:1, change_note:'',
  title:'Подготовка к занятию', intro:'Полезные материалы', acknowledged:false, completed:false,
  assessment_version_id:null, latest_attempt_id:null, latest_attempt_state:null, reacknowledgement_required:false,
  lessons:[{id:'read',key:'read',lesson_id:'read-source',minutes:5,mode:'feed',title:'Знакомство',completed:true},{id:'next',key:'next',lesson_id:'next-source',minutes:10,mode:'feed',title:'На занятии',completed:false}]};
const learning: Preparation = {assignments:[track], introduction_completed:false, booking_requires_introduction:false};
const basePreparation: Schemas['AssignmentPreparationView'] = {
  assignment_id:'first', assignment_version:1, title:'Мастерская', status:'confirmed', starts_at:'2026-10-22T09:00:00Z', ends_at:'2026-10-22T11:00:00Z',
  timezone:'Europe/Moscow', location:'Вход со двора', role_title:'Помощник', tasks:'Помочь разложить материалы', group_briefing_available:true,
  contacts:[{role:'Ведущий',display_name:'Юлия Волкова'},{role:'Координатор',display_name:'Мария Петрова'}],
  checklist:[{key:'read',title:'Прочитать памятку',checked:true},{key:'bring',title:'Взять сменную обувь',checked:false}],
  checklist_version:1, questions:[], allowed_actions:['cancel'], version:1,
};
const participant = (id: string, display_name: string): Schemas['SafeParticipant'] => ({id, display_name, about:'', birth_year:null, communication:'', interests:'', lifecycle:'active', photo_asset_id:null, support:'', communication_tags:[], interests_tags:[], support_tags:[], version:1});
const briefing: Schemas['AssignmentGroupBriefing'] = {assignment_id:'first', groups:[{id:'group', title:'Арт-группа'}], items:[participant('p1','Саша'),participant('p2','Лена'),participant('p3','Паша')]};
const need = (changes: Partial<Schemas['VolunteerEventNeed']> = {}): Schemas['VolunteerEventNeed'] => ({id:'need', version:1, role_id:'role', role_title:'Ассистент педагога', task:'', required:4, confirmed:2, missing:2, points_multiplier:1, approval_policy:'self_confirmation', preparation_requirements:[], allowed_actions:['sign-up'], ...changes});
const eventCard = (title: string, changes: Partial<Schemas['VolunteerEventCard']> = {}): Schemas['VolunteerEventCard'] => ({
  occurrence_id:title, series_id:'series', title, program:'Творческие мастерские', kind:'activity', format:'onsite', location:'Мастерская фонда', audience:'',
  status:'scheduled', starts_at:'2026-10-24T11:00:00Z', ends_at:'2026-10-24T13:00:00Z', timezone:'Europe/Moscow', best_need_id:'need', reasons:[], full:false, conflict:false,
  needs:[need()], ...changes,
});
const steps = (current: number): Schemas['LevelView']['steps'] => [['first_steps','Первые шаги',null],['team','В команде',1200],['friend','Друг фонда',3000],['pillar','Опора фонда',6000]]
  .map(([key, title, minutes], index) => ({key:key as string, title:title as string, minutes:minutes as number | null, reached:index <= current, current:index === current}));
const blankHours: Schemas['HoursView'] = {total_minutes:0, confirmed_assignments:0, pending_minutes:0, ledger_pending:0, entries:[], manual_requests:[], achievements:[], gratitudes:[],
  level:{key:null, title:null, next_title:'Первые шаги', next_minutes:null, letter_hint:false, steps:steps(-1)}, points:{balance:100, earned:100, reserved:0, spent:0, can_request:false, history:[]}};
const teamHours: Schemas['HoursView'] = {...blankHours, total_minutes:2760, confirmed_assignments:12,
  level:{key:'team', title:'В команде', next_title:'Друг фонда', next_minutes:3000, letter_hint:false, steps:steps(1)}, points:{...blankHours.points, balance:460}};
const profileView = (display_name: string): Schemas['ProfileView'] => ({user_id:'volunteer', display_name, version:1, about:'', lifecycle:'active', paused_until:null, photo_asset_id:null, ai_about:false, ai_skills:false, ai_interests:false, tags:[], contacts:[], revisions:[]});

let feed: Schemas['VolunteerEventFeed'];
let hours: Schemas['HoursView'];
let profile: Schemas['ProfileView'];
let preparation: Schemas['AssignmentPreparationView'];
let rows: AssignmentParticipation[];
/** The past year read by the newcomer check; by default one confirmed занятие already happened. */
let pastRows: AssignmentParticipation[];
let nextRows: AssignmentParticipation[] | undefined;
let learningError: Error | undefined;
let nextPageError: Error | undefined;
let commands: {path: string; body: unknown}[];
let apiSpy: MockInstance<typeof transport.api>;
const clients: QueryClient[] = [];
beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(now);
  rows = []; pastRows = [assignment({id:'past', starts_at:'2026-10-10T09:00:00Z', ends_at:'2026-10-10T11:00:00Z'})]; hours = teamHours; profile = profileView('Анна Смирнова'); preparation = basePreparation; nextRows = undefined; learningError = undefined; nextPageError = undefined; commands = [];
  feed = {algorithm_version:'rules-v3', can_sign_up:true, items:[]};
  apiSpy = vi.spyOn(transport, 'api').mockImplementation(async <T,>(path: string, options?: transport.ApiOptions): Promise<T> => {
    if (options?.method === 'POST') {
      commands.push({path, body:options.body});
      const [, id, action] = /\/assignments\/([^/]+)\/([a-z-]+)$/.exec(path) ?? [];
      if (action === 'confirm') rows = rows.map(row => row.id === id ? {...row, status:'confirmed', version:row.version + 1, allowed_actions:['cancel']} : row);
      if (action === 'decline' || action === 'cancel') rows = rows.filter(row => row.id !== id);
      if (action === 'questions') preparation = {...preparation, questions:[{id:'late', kind:'question', text:'Опаздываю на занятие', restricted:false, public_answer:'', created_at:'2026-10-22T08:00:00Z', answered_at:null, version:1}]};
      return {} as T;
    }
    if (path.startsWith('/me/events?')) return feed as T;
    if (path.startsWith('/me/schedule?') && path.includes('state=all')) return {items:pastRows, next_cursor:null} as T;
    if (path.startsWith('/me/schedule?')) {
      if (path.includes('cursor=next') && nextPageError) throw nextPageError;
      return (path.includes('cursor=next') ? {items:nextRows ?? [], next_cursor:null} : {items:rows, next_cursor:nextRows ? 'next' : null}) as T;
    }
    if (path === '/api/v1/me/preparation') {if (learningError) throw learningError; return learning as T;}
    const memo = /^\/me\/assignments\/([^/]+)\/preparation$/.exec(path);
    if (memo) return {...preparation, assignment_id:memo[1]} as T;
    if (path === '/me/assignments/first/group-briefing') return briefing as T;
    if (path === '/me/hours') return hours as T;
    if (path === '/me/profile') return profile as T;
    throw new Error(`Unexpected home API: ${path}`);
  });
});
afterEach(() => {cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks();});
function view() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}, mutations:{retry:false}}}); clients.push(client);
  return render(<QueryClientProvider client={client}><MemoryRouter><HomePage/></MemoryRouter></QueryClientProvider>);
}
const heroSection = () => document.querySelector('.card-hero') as HTMLElement;
const reads = (prefix: string) => apiSpy.mock.calls.filter(call => String(call[0]).startsWith(prefix));

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
  it('labels dates in the event timezone and picks the hero state from status and day', () => {
    expect(assignmentWhen(assignment(), now)).toMatchObject({today:true, date:'Сегодня', day:'сегодня', time:'12:00', range:'12:00–14:00', dayNumber:'22', weekday:'чт'});
    expect(assignmentWhen(assignment(tomorrow), now)).toMatchObject({today:false, date:'Пт, 23 октября', day:'23 октября', time:'12:00', dayNumber:'23', weekday:'пт'});
    expect(assignmentWhen(assignment({starts_at:'2026-10-21T20:00:00Z', ends_at:'2026-10-21T23:00:00Z'}), now).today).toBe(true);
    expect(heroKind(assignment(), now)).toBe('today');
    expect(heroKind(assignment(tomorrow), now)).toBe('nearest');
    expect(heroKind(assignment({status:'invited'}), now)).toBe('invitation');
    expect([heroEyebrow('nearest', false), heroEyebrow('invitation', false), heroEyebrow('invitation', true), heroEyebrow('today', true)])
      .toEqual(['Ближайшее занятие', 'Тебя приглашают', 'Твой первый выход', 'Сегодня']);
    expect(homeScheduleRange(now)).toEqual({from:'2026-10-22', to:'2027-01-19'});
  });
  it('derives names, the newcomer path, places and level copy only from server data', () => {
    expect([firstName('Анна Смирнова'), firstName('[ДЕМО] Анна Демонстрационная'), firstName('Волонтёр'), firstName(undefined)]).toEqual(['Анна', 'Анна', '', '']);
    expect(startPath('invited').map(step => step.state)).toEqual(['done', 'now', '', '', '']);
    expect(startPath('confirmed', 'Юлия', 'Мария').map(step => [step.state, step.text])).toEqual([
      ['done', 'Роль подобрали'], ['done', 'Ты придёшь'], ['now', 'Юлия рядом всё занятие'], ['', 'Мария позвонит'], ['', 'Регулярно, другая роль или пауза']]);
    expect([1, 2, 3].map(placesFor)).toEqual([{label:'Осталось одно место', tone:'few'}, {label:'Осталось два места', tone:'few'}, {label:'Есть места', tone:''}]);
    expect(homePastRange(now)).toEqual({from:'2025-10-21', to:'2026-10-22'});
    expect(hadConfirmedPast([assignment({ends_at:'2026-10-21T20:00:00Z'})], now)).toBe(true);
    expect(hadConfirmedPast([assignment({ends_at:'2026-10-21T20:00:00Z', status:'invited'}), assignment({ends_at:'2026-10-21T20:00:00Z', occurrence_status:'cancelled'}), assignment()], now)).toBe(false);
    expect(pickedEvents({...feed, can_sign_up:false, items:[eventCard('a')]})).toEqual([]);
    expect(pickedEvents({...feed, items:[eventCard('a'), eventCard('mine', {my_assignment:{id:'x', approved_at:null, origin:'self', staffing_need_id:'need', status:'confirmed', version:1}}), eventCard('b', {full:true}), eventCard('c', {conflict:true}), eventCard('d'), eventCard('e'), eventCard('f')]}).map(card => card.title)).toEqual(['a', 'd', 'e']);
    expect(pathLine(teamHours)).toBe('46 часов помощи, до «Друг фонда» 4 часа');
    expect(pathLine(blankHours)).toBe('Уровень «Первые шаги» откроется после первого занятия');
    expect(lateSent({...basePreparation, questions:[{id:'q', kind:'question', text:'Опаздываю на занятие', restricted:false, public_answer:'', created_at:'', answered_at:null, version:1}]})).toBe(true);
    expect(learningDestination({...track, lessons:[]})).toBe('/academy');
    expect(learningDestination({...track, lessons:[], assessment_version_id:'assessment'})).toBe('/academy/lessons/assessment?assignment=learning');
  });
});

describe('volunteer home', () => {
  it('greets by the first name from the profile and never invents one', async () => {
    view(); expect(await screen.findByRole('heading', {level:1, name:'Привет, Анна!'})).toBeTruthy();
    cleanup(); profile = profileView('Волонтёр');
    view(); await screen.findByRole('heading', {name:'Пока ничего не запланировано'});
    expect(screen.getByRole('heading', {level:1}).textContent).toBe('Привет!');
  });
  it('loads all assignment pages before choosing the hero and shows the day of the занятие with the group', async () => {
    rows=[assignment({id:'later',title:'Позже',...tomorrow})]; nextRows=[assignment()];
    view();
    await userEvent.setup().click(await screen.findByRole('button', {name:'Загрузить ещё занятия'}));
    const card = (await screen.findByRole('heading', {name:'12:00–14:00'})).closest('section') as HTMLElement;
    expect(within(card).getByText('Сегодня')).toBeTruthy();
    await within(card).findByText('Мастерская, Мастерская фонда. Юлия встретит у входа.');
    expect(within(card).getByRole('link', {name:'Открыть памятку'}).getAttribute('href')).toBe('/my/assignments/first/preparation');
    expect(within(card).getByRole('button', {name:'Опаздываю'})).toBeTruthy();
    const group = (await screen.findByRole('heading', {name:'Сегодня в группе'})).closest('section') as HTMLElement;
    await within(group).findByText('Саша, Лена, Паша');
    expect(within(group).getByRole('link', {name:'Как общаться с ребятами'}).getAttribute('href')).toBe('/me/group?assignment_id=first');
    expect(within(group).getByText('Юлия, ведущий')).toBeTruthy();
    expect(within(group).getByText('Встретит у входа')).toBeTruthy();
    expect(within(group).getByRole('link', {name:'Написать'}).getAttribute('href')).toBe('/messages');
    const progress = screen.getByRole('progressbar', {name:'Пройдено уроков'});
    expect([progress.getAttribute('aria-valuenow'), progress.getAttribute('aria-valuemax')]).toEqual(['1', '2']);
    expect(screen.getByRole('link', {name:'Продолжить'}).getAttribute('href')).toBe('/academy/lessons/next?assignment=learning');
    expect(screen.queryByText('Подобрано для тебя')).toBeNull();
    expect(reads('/me/schedule?').some(call => String(call[0]).includes('cursor=next'))).toBe(true);
    expect(reads('/me/schedule?').filter(call => !String(call[0]).includes('state=all')).every(call => String(call[0]).includes('from=2026-10-22&to=2027-01-19&timezone=Europe/Moscow&state=active'))).toBe(true);
    expect(reads('/me/schedule?').some(call => String(call[0]).includes('from=2025-10-21&to=2026-10-22&timezone=Europe/Moscow&state=all'))).toBe(true);
    expect(apiSpy.mock.calls.every(call => !call[1] || !call[1].method || call[1].method === 'GET')).toBe(true);
  });
  it('tells the coordinator about being late with an ordinary question and keeps the note from the server', async () => {
    rows=[assignment()]; view();
    const card = (await screen.findByRole('heading', {name:'12:00–14:00'})).closest('section') as HTMLElement;
    await userEvent.setup().click(within(card).getByRole('button', {name:'Опаздываю'}));
    expect(await within(card).findByText('Мария знает, что ты задержишься')).toBeTruthy();
    expect(commands).toEqual([{path:'/me/assignments/first/questions', body:{kind:'question', text:'Опаздываю на занятие', restricted:false}}]);
    expect(within(card).queryByRole('button', {name:'Опаздываю'})).toBeNull();
    cleanup(); view();
    expect(await screen.findByText('Мария знает, что ты задержишься')).toBeTruthy();
    expect(screen.queryByRole('button', {name:'Опаздываю'})).toBeNull();
  });
  it('shows the nearest confirmed занятие and cancels it only after the inline confirmation', async () => {
    rows=[assignment(tomorrow)]; view();
    const card = (await screen.findByRole('heading', {name:'Пт, 23 октября, 12:00'})).closest('section') as HTMLElement;
    expect(within(card).getByText('Ближайшее занятие')).toBeTruthy();
    expect(within(card).getByRole('link', {name:'Подготовиться'}).getAttribute('href')).toBe('/my/assignments/first/preparation');
    const user = userEvent.setup();
    await user.click(within(card).getByRole('button', {name:'Не смогу'}));
    expect(within(card).getByRole('group', {name:'Предупредить координатора, что не сможешь?'})).toBeTruthy();
    await user.click(within(card).getByRole('button', {name:'Я приду'}));
    expect(commands).toEqual([]);
    await user.click(within(card).getByRole('button', {name:'Не смогу'}));
    await user.click(within(card).getByRole('button', {name:'Да, не смогу'}));
    expect(await screen.findByRole('heading', {name:'Подберём другую дату'})).toBeTruthy();
    expect(screen.getByText('Координатор знает, что 23 октября ты не сможешь.')).toBeTruthy();
    expect(commands).toEqual([{path:'/assignments/first/cancel', body:{expected_version:1}}]);
    expect(screen.queryByText('Как проходит начало')).toBeNull();
  });
  it('answers the nearest invitation in the hero and does not read the memo before confirmation', async () => {
    rows=[assignment({status:'invited', ...tomorrow})]; view();
    const card = (await screen.findByRole('heading', {name:'Пт, 23 октября, 12:00'})).closest('section') as HTMLElement;
    expect(within(card).getByText('Тебя приглашают')).toBeTruthy();
    expect(reads('/me/assignments/first/preparation')).toHaveLength(0);
    await userEvent.setup().click(within(card).getByRole('button', {name:'Я приду'}));
    expect(await within(heroSection()).findByRole('link', {name:'Подготовиться'})).toBeTruthy();
    expect(commands).toEqual([{path:'/assignments/first/confirm', body:{expected_version:1}}]);
  });
  it('walks a newcomer through the first steps from the real status', async () => {
    hours=blankHours; pastRows=[]; rows=[assignment({status:'invited', ...tomorrow})];
    feed={...feed, items:[eventCard('Арт-суббота')]};
    view();
    await waitFor(() => expect(within(heroSection()).getByText('Твой первый выход')).toBeTruthy());
    const path = (screen.getByRole('heading', {name:'Как проходит начало'})).closest('section') as HTMLElement;
    const items = within(path).getAllByRole('listitem');
    expect(items).toHaveLength(5);
    expect(items[1].getAttribute('aria-current')).toBe('step');
    expect(items[0].className).toContain('done');
    expect(within(heroSection()).getByRole('button', {name:'Я приду'})).toBeTruthy();
    expect(within(heroSection()).getByRole('link', {name:'Подробнее'}).getAttribute('href')).toBe('/my/assignments/first');
    expect(within(heroSection()).queryByRole('button', {name:'Не смогу'})).toBeNull();
    expect(screen.queryByText('Подобрано для тебя')).toBeNull();
    const card = await screen.findByRole('link', {name:'Мой путь'});
    expect(within(card).getByRole('heading', {name:'Первое занятие впереди'})).toBeTruthy();
    expect(within(card).getByText('Уровень «Первые шаги» откроется после первого занятия')).toBeTruthy();
    cleanup(); rows=[assignment(tomorrow)]; view();
    const confirmed = (await screen.findByRole('heading', {name:'Как проходит начало'})).closest('section') as HTMLElement;
    await within(confirmed).findByText('Юлия рядом всё занятие');
    expect(within(confirmed).getAllByRole('listitem')[2].getAttribute('aria-current')).toBe('step');
    expect(within(heroSection()).getByText(/Тебя встретит Юлия\./)).toBeTruthy();
  });
  it('counts as a newcomer only without a confirmed занятие in the past, whatever the hours say', async () => {
    hours=blankHours; rows=[assignment({status:'invited', ...tomorrow})];
    view();
    const card = (await screen.findByRole('heading', {name:'Пт, 23 октября, 12:00'})).closest('section') as HTMLElement;
    await waitFor(() => expect(reads('/me/schedule?').some(call => String(call[0]).includes('state=all'))).toBe(true));
    expect(within(card).getByText('Тебя приглашают')).toBeTruthy();
    expect(screen.queryByText('Как проходит начало')).toBeNull();
    expect(within(card).getByRole('button', {name:'Не смогу'})).toBeTruthy();
  });
  it('shows an own request or a freed reserve place as waiting for the coordinator, with a way to withdraw', async () => {
    rows=[assignment({id:'mine', status:'invited', origin:'self', ...tomorrow})];
    view();
    const card = (await screen.findByText('Ждёт ответа координатора')).closest('section') as HTMLElement;
    expect(card.className).toContain('calm');
    expect(within(card).getByRole('link', {name:'Подробнее'}).getAttribute('href')).toBe('/my/assignments/mine');
    await userEvent.setup().click(within(card).getByRole('button', {name:'Отменить заявку'}));
    expect(commands).toEqual([{path:'/assignments/mine/decline', body:{expected_version:1}}]);
    cleanup();
    rows=[assignment({id:'offer', status:'invited', origin:'reserve', ...tomorrow})];
    view();
    const offer = (await screen.findByText('Освободилось место из резерва')).closest('section') as HTMLElement;
    expect(within(offer).getByText('Координатор подтвердит участие.')).toBeTruthy();
    expect(within(offer).getByRole('button', {name:'Не смогу'})).toBeTruthy();
    expect(within(offer).queryByRole('button', {name:'Я приду'})).toBeNull();
  });
  it('lists other invitations with the points pill and answers each one inline', async () => {
    rows=[assignment({status:'invited', ...tomorrow}), assignment({id:'bazaar', status:'invited', title:'Шерстяной базар', starts_at:'2026-10-25T08:00:00Z', ends_at:'2026-10-25T12:00:00Z', points_multiplier:1.5}),
      assignment({id:'fair', status:'invited', title:'Ярмарка', starts_at:'2026-10-26T08:00:00Z', ends_at:'2026-10-26T12:00:00Z'}),
      assignment({id:'pending', status:'invited', origin:'self', title:'Своя заявка', starts_at:'2026-10-27T08:00:00Z', ends_at:'2026-10-27T12:00:00Z'})];
    view();
    const section = (await screen.findByRole('heading', {name:'Тебя приглашают', level:2})).closest('section') as HTMLElement;
    const list = within(section).getAllByRole('link').map(link => link.textContent);
    expect(list).toEqual(['Шерстяной базар', 'Ярмарка']);
    expect(within(section).getAllByText('Баллы ×1,5')).toHaveLength(1);
    const [bazaar, fair] = [...section.querySelectorAll<HTMLElement>('.home-invite')];
    expect(bazaar.textContent).toContain('11:00–15:00, Мастерская фонда');
    expect(bazaar.querySelector('.day')!.className).toMatch(/^day [yobgv]$/);
    const user = userEvent.setup();
    await user.click(within(bazaar).getByRole('button', {name:'Я приду'}));
    expect(await within(bazaar).findByText('Ты придёшь')).toBeTruthy();
    await user.click(within(fair).getByRole('button', {name:'Не смогу'}));
    await user.click(within(fair).getByRole('button', {name:'Да, не смогу'}));
    expect(await within(fair).findByText('Ты не придёшь')).toBeTruthy();
    expect(commands).toEqual([{path:'/assignments/bazaar/confirm', body:{expected_version:1}}, {path:'/assignments/fair/decline', body:{expected_version:1}}]);
    expect(within(heroSection()).getByText('Тебя приглашают')).toBeTruthy();
  });
  it('shows a calm empty hero pointing to events and the own schedule, or to the meeting while sign-up is locked', async () => {
    view(); await screen.findByRole('heading', {name:'Пока ничего не запланировано'});
    expect(heroSection().className).toContain('calm');
    expect(screen.getByRole('link', {name:'Все мероприятия'}).getAttribute('href')).toBe('/events');
    expect(screen.getByRole('link', {name:'Мои занятия'}).getAttribute('href')).toBe('/my/schedule');
    cleanup();
    feed={algorithm_version:'rules-v3', can_sign_up:false, locked_reason:'meeting_required', locked_message:'Записаться можно после встречи с координатором.', items:[eventCard('Арт-суббота')]};
    view();
    await screen.findByText('Записаться можно после встречи с координатором.');
    expect(screen.getByRole('link', {name:'Встреча с координатором'}).getAttribute('href')).toBe('/interviews');
    expect(screen.queryByText('Подобрано для тебя')).toBeNull();
  });
  it('shows level, hours and points from the server on the my path card', async () => {
    hours={...teamHours, total_minutes:2760};
    view(); const card = await screen.findByRole('link', {name:'Мой путь'});
    expect(card.getAttribute('href')).toBe('/hours');
    expect(within(card).getByRole('heading', {name:'В команде'})).toBeTruthy();
    expect(within(card).getByText('46 часов помощи, до «Друг фонда» 4 часа')).toBeTruthy();
    expect(within(card).getByText('460 баллов')).toBeTruthy();
    expect(within(card).getByText('В команде', {selector:'.cur'})).toBeTruthy();
    expect(card.querySelectorAll('.mp-steps i.on')).toHaveLength(2);
    expect(screen.getByRole('link', {name:/Не знаешь, как поступить на занятии/}).getAttribute('href')).toBe('/mentor');
  });
  it('retains the hero when learning fails and retries only the failed read', async () => {
    rows=[assignment(tomorrow)]; learningError=new Error('Обучение временно недоступно'); view();
    await screen.findByText('Обучение временно недоступно');
    expect(await screen.findByRole('link', {name:'Подготовиться'})).toBeTruthy();
    learningError=undefined;
    await userEvent.setup().click(screen.getByRole('button', {name:'Попробовать ещё раз'}));
    await waitFor(() => expect(screen.queryByText('Обучение временно недоступно')).toBeNull());
    expect(screen.getByRole('link', {name:'Продолжить'})).toBeTruthy();
  });
  it('does not misrepresent a failed list or missing pagination page as an empty result', async () => {
    rows=[assignment({id:'later', ...tomorrow})]; nextRows=[assignment()]; nextPageError=new Error('Приглашения временно недоступны'); view();
    await screen.findByRole('heading', {name:'Расписание загружено не полностью'});
    expect(reads('/me/schedule?').some(call => String(call[0]).includes('cursor=next'))).toBe(false);
    await userEvent.setup().click(screen.getByRole('button', {name:'Загрузить ещё занятия'}));
    await screen.findByText('Приглашения временно недоступны');
    expect(screen.queryByRole('heading', {name:'Пока ничего не запланировано'})).toBeNull();
    expect(screen.queryByText('Ближайшее занятие')).toBeNull();
    nextPageError=undefined;
    await userEvent.setup().click(screen.getByRole('button', {name:'Попробовать ещё раз'}));
    expect(await screen.findByRole('link', {name:'Открыть памятку'})).toBeTruthy();
  });
  it('shows the top three open events from the server-ranked feed with places, never full ones or a score', async () => {
    feed={algorithm_version:'rules-v3', can_sign_up:true, items:[eventCard('Арт-суббота', {needs:[need({missing:1})]}), eventCard('Выезд', {full:true}), eventCard('Шерстяной Базар', {needs:[need({missing:5})]}), eventCard('Экскурсия', {needs:[need({points_multiplier:1.5})]}), eventCard('Онлайн-афиша')]};
    view();
    const section = (await screen.findByRole('heading', {name:'Подобрано для тебя'})).closest('section') as HTMLElement;
    const tiles = within(section).getAllByRole('link').filter(link => link.getAttribute('href')?.startsWith('/events/'));
    expect(tiles.map(link => link.querySelector('.h3')?.textContent)).toEqual(['Арт-суббота', 'Шерстяной Базар', 'Экскурсия']);
    expect(tiles[0].getAttribute('href')).toBe('/events/Арт-суббота');
    expect(tiles.map(link => link.querySelector('.places')?.textContent)).toEqual(['Осталось одно место', 'Есть места', 'Осталось два места']);
    expect(tiles[0].querySelector('.when')?.textContent).toBe('Сб, 24 октября, 14:00');
    expect(within(section).getByRole('link', {name:'Все мероприятия'}).getAttribute('href')).toBe('/events');
    // The feed's own tile: the points pill takes the arrow's place, as in «Все мероприятия».
    expect(tiles.map(link => link.querySelector('.ev-pts')?.textContent ?? '')).toEqual(['', '', 'Баллы ×1,5']);
    expect(tiles.map(link => Boolean(link.querySelector('.tile-foot > .ic')))).toEqual([true, true, false]);
    expect(section.textContent).not.toMatch(/score|%|Почему так/i);
  });
});
