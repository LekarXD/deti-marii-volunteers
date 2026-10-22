// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi,type MockInstance} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import * as transport from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {PersonalSchedulePage} from './PersonalSchedulePage';

type Assignment = components['schemas']['AssignmentParticipationView'];
type Card = components['schemas']['VolunteerEventCard'];
type Reserve = components['schemas']['VolunteerReserveItem'];
const assignment = (id: string, title: string, starts_at: string, changes: Partial<Assignment> = {}): Assignment => ({id, version:2, user_id:'me', display_name:'Мария', occurrence_id:`occ-${id}`, staffing_need_id:'need',
  title, role_title:'Ассистент педагога', starts_at, ends_at:new Date(Date.parse(starts_at)+2*3600_000).toISOString(), timezone:'Europe/Moscow', location:'мастерская на Дмитровке',
  status:'confirmed', origin:'invitation', occurrence_status:'scheduled', approved_at:'2026-10-01T10:00:00Z', confirmed_at:'2026-10-02T10:00:00Z', conditions_version:1, approval_required:false, points_multiplier:1,
  readiness:[], allowed_actions:['cancel'], history:[], attendance:null, ...changes});
const card = (title: string, starts_at: string, changes: Partial<Card> = {}): Card => ({occurrence_id:title, series_id:title, title, program:'Творческие мастерские', kind:'activity', format:'onsite',
  location:'Грибаново', audience:'Взрослые участники', status:'scheduled', starts_at, ends_at:new Date(Date.parse(starts_at)+4*3600_000).toISOString(), timezone:'Europe/Moscow',
  needs:[{id:`need-${title}`, version:3, role_id:'role', role_title:'Ассистент педагога', task:'Помогать ведущей.', required:4, confirmed:2, missing:2, approval_policy:'self_confirmation', preparation_requirements:[], allowed_actions:['sign-up']}],
  best_need_id:`need-${title}`, reasons:[], full:false, conflict:false, ...changes});
let schedule: Assignment[];
let feed: components['schemas']['VolunteerEventFeed'];
let reflected: Set<string>;
let reserves: Reserve[];
const reserve = (id: string, title: string, starts_at: string): Reserve => ({kind:'reserve', reserve_id:id, version:1, position:2, state:'waiting', occurrence_id:`occ-${id}`, staffing_need_id:'need', title, role_title:'Ассистент мастера',
  starts_at, ends_at:new Date(Date.parse(starts_at)+2*3600_000).toISOString(), location:'Новинский бульвар', timezone:'Europe/Moscow', allowed_actions:['leave']});
let apiSpy: MockInstance<typeof transport.api>;
const clients: QueryClient[] = [];

beforeEach(() => {
  vi.useFakeTimers({now:new Date('2026-10-22T09:00:00Z'), toFake:['Date']});
  schedule = [];
  reflected = new Set();
  reserves = [];
  feed = {algorithm_version:'rules-v3', can_sign_up:true, items:[]};
  apiSpy = vi.spyOn(transport, 'api').mockImplementation(async <T,>(path: string, init?: {body?: unknown}): Promise<T> => {
    if (path.startsWith('/me/schedule?')) return {items:schedule, next_cursor:null} as T;
    if (path.startsWith('/me/events?')) return feed as T;
    if (path === '/me/reserves') return {items:reserves} as T;
    if (/^\/api\/v1\/reserves\/[^/]+\/leave$/.test(path)) return {...reserves[0], state:'closed'} as T;
    const reflection = /^\/me\/assignments\/([^/]+)\/reflection$/.exec(path);
    if (reflection) return {assignment_id:reflection[1], id:null, can_submit:!reflected.has(reflection[1]), submitted_at:reflected.has(reflection[1]) ? '2026-10-19T10:00:00Z' : null} as T;
    if (/\/assignments\/[^/]+\/(confirm|decline|cancel)$/.test(path)) return {...schedule[0], version:3} as T;
    if (path.endsWith('/sign-up')) return {...assignment('new', 'Арт-суббота', '2026-10-31T11:00:00Z'), version:1, body:init?.body} as T;
    throw new Error(`Unexpected schedule API: ${path}`);
  });
});
afterEach(() => {cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); vi.useRealTimers();});
function view(path = '/my/schedule') {
  const client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/my/schedule" element={<PersonalSchedulePage/>}/></Routes></MemoryRouter></QueryClientProvider>);
}
const section = (name: string) => screen.getByRole('heading', {level:2, name}).closest('section') as HTMLElement;
const titles = (root: HTMLElement) => Array.from(root.querySelectorAll('.rowi-title')).map(node => node.textContent);

describe('volunteer schedule', () => {
  it('shows the invitation, the rows ahead with exception marks only, open places on free days and the past', async () => {
    schedule = [
      assignment('paint', 'Живопись с «Подсолнухами»', '2026-10-24T09:00:00Z', {status:'invited', confirmed_at:null, allowed_actions:['confirm','decline']}),
      assignment('tour', 'Экскурсия «Люди решают»', '2026-10-28T13:00:00Z', {points_multiplier:1.5}),
      assignment('photo', 'Съёмка выставки', '2026-10-30T15:00:00Z', {status:'invited', origin:'self', approval_required:true, approved_at:null, confirmed_at:null, allowed_actions:['confirm','decline']}),
      assignment('open-day', 'День открытых дверей', '2026-11-05T15:00:00Z', {status:'cancelled', occurrence_status:'cancelled', allowed_actions:[]}),
      assignment('gone', 'Отказ', '2026-11-06T15:00:00Z', {status:'declined', allowed_actions:[]}),
      assignment('fair', 'Ярмарка', '2026-10-18T08:00:00Z', {attendance:{id:'a', version:1, outcome:'attended', minutes:300, ledger_state:'pending'}}),
      assignment('art', 'Арт-суббота', '2026-10-17T11:00:00Z', {attendance:{id:'b', version:1, outcome:'attended', minutes:240, ledger_state:'posted'}}),
    ];
    reflected.add('art');
    feed.items = [
      card('Арт-суббота', '2026-10-31T11:00:00Z'),
      card('Шерстяной базар', '2026-10-24T14:00:00Z'),
    ];
    reserves = [reserve('felt', 'Мастер-класс по валянию', '2026-10-31T08:00:00Z')];
    view();
    expect(await screen.findByText('Тебя приглашают')).toBeTruthy();
    expect(screen.getByRole('heading', {level:1, name:'Мероприятия'})).toBeTruthy();
    expect(screen.getByRole('link', {name:'Мои занятия'}).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('heading', {level:2, name:'Сб, 24 октября, 12:00'})).toBeTruthy();
    expect(screen.getByText('Живопись с «Подсолнухами», мастерская на Дмитровке. Ассистент педагога')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/московскому времени|Отмены и отказы|Сегодня|смен|·/);

    const ahead = section('Впереди');
    expect(titles(ahead)).toEqual(['Живопись с «Подсолнухами»', 'Экскурсия «Люди решают»', 'Съёмка выставки', 'Мастер-класс по валянию']);
    expect(within(ahead).getByText('Ждёт ответа')).toBeTruthy();
    expect(within(ahead).getByText('Ждёт ответа координатора')).toBeTruthy();
    expect(within(ahead).getByText('В резерве')).toBeTruthy();
    const tour = within(ahead).getByText('Экскурсия «Люди решают»').closest('a') as HTMLElement;
    expect(tour.getAttribute('href')).toBe('/my/assignments/tour/preparation');
    expect(within(tour).getByText('Баллы ×1,5')).toBeTruthy();
    expect(tour.querySelector('.st-mark')).toBeNull();
    expect(within(tour).getByText('16:00–18:00, мастерская на Дмитровке')).toBeTruthy();
    expect(within(ahead).getByText('Живопись с «Подсолнухами»').closest('a')!.getAttribute('href')).toMatch(/^\/my\/assignments\/paint\?schedule_return=/);
    expect(within(ahead).getByText('Мастер-класс по валянию').closest('a')!.getAttribute('href')).toBe('/events/occ-felt');
    const user = userEvent.setup();
    await user.click(within(ahead).getByRole('button', {name:'Показать все (5)'}));
    expect(titles(ahead)).toContain('День открытых дверей');
    expect(titles(ahead)).not.toContain('Отказ');
    expect(within(ahead).getByText('День открытых дверей').closest('a')!.className).toContain('is-off');
    expect(within(ahead).getByText('Отменено фондом')).toBeTruthy();

    const offers = section('Можно записаться');
    expect(within(offers).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/events', '/events/Арт-суббота']);
    expect(within(offers).getByText('Осталось два места')).toBeTruthy();
    await user.click(within(offers).getByRole('button', {name:'Почему так'}));
    expect(within(offers).getByText('Здесь только то, что не пересекается с твоими занятиями.')).toBeTruthy();
    expect(within(offers).getByText('Выше то, что подходит тебе: навыки и направления из анкеты, удобное время и группы, где ты уже помогаешь.')).toBeTruthy();
    expect(within(offers).getAllByRole('link').filter(link => link.classList.contains('tile')).every(link => link.querySelector('.tile-foot > .ic'))).toBe(true);

    const past = section('Прошедшие');
    await user.click(within(past).getByRole('button', {name:'Показать (2)'}));
    expect(titles(past)).toEqual(['Ярмарка', 'Арт-суббота']);
    expect(within(past).getByRole('img', {name:'Ждёт подтверждения'}).parentElement!.textContent).toContain('5 ч');
    expect(within(past).getByRole('img', {name:'Засчитано'}).parentElement!.textContent).toContain('4 ч');
    const reflect = await within(past).findByRole('link', {name:'Как прошло?'});
    expect(reflect.getAttribute('href')).toBe('/my/assignments/fair/reflection');
    expect(within(past).getAllByRole('link', {name:'Как прошло?'})).toHaveLength(1);

    expect(screen.getByRole('link', {name:'Поставить паузу'}).getAttribute('href')).toBe('/profile?tab=pause');
    await user.click(screen.getByRole('button', {name:'Я приду'}));
    const call = apiSpy.mock.calls.find(([path]) => String(path).endsWith('/confirm'))!;
    expect(call[0]).toBe('/api/v1/assignments/paint/confirm');
    expect(call[1]).toMatchObject({method:'POST', body:{expected_version:2}});
  }, 15000);

  it('lets the volunteer answer every coordinator invitation and marks only own requests as waiting for the coordinator', async () => {
    schedule = [
      assignment('tour', 'Экскурсия «Люди решают»', '2026-10-28T13:00:00Z', {status:'invited', approval_required:true, approved_at:null, confirmed_at:null, allowed_actions:['confirm','decline']}),
      assignment('autumn', 'Осень в городе', '2026-11-02T08:00:00Z', {status:'invited', origin:'reserve', approved_at:null, confirmed_at:null, allowed_actions:['confirm','decline']}),
      assignment('photo', 'Съёмка выставки', '2026-10-30T15:00:00Z', {status:'invited', origin:'self', approved_at:null, confirmed_at:null, allowed_actions:['confirm','decline']}),
    ];
    view();
    expect(await screen.findByText('Тебя приглашают')).toBeTruthy();
    expect(screen.getByRole('heading', {level:2, name:'Ср, 28 октября, 16:00'})).toBeTruthy();
    expect(screen.getByRole('button', {name:'Я приду'})).toBeTruthy();
    const ahead = section('Впереди');
    const mark = (title: string) => within(ahead).getByText(title).closest('a')!.querySelector('.st-mark')?.textContent;
    expect(mark('Экскурсия «Люди решают»')).toBe('Ждёт ответа');
    expect(mark('Съёмка выставки')).toBe('Ждёт ответа координатора');
    expect(mark('Осень в городе')).toBe('Освободилось место из резерва');
  });

  it('asks why before telling the coordinator and then shows that a replacement is being found', async () => {
    schedule = [assignment('paint', 'Живопись с «Подсолнухами»', '2026-10-24T09:00:00Z')];
    view();
    expect(await screen.findByText('Ближайшее занятие')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Подготовиться'}).getAttribute('href')).toBe('/my/assignments/paint/preparation');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', {name:'Не смогу'}));
    expect(screen.getByRole('heading', {name:'Не сможешь прийти?'})).toBeTruthy();
    expect(within(screen.getByRole('radiogroup', {name:'Почему не получится'})).getAllByRole('radio').map(radio => radio.textContent)).toEqual(['Болезнь', 'Работа', 'Семейные дела', 'Другое']);
    const send = screen.getByRole('button', {name:'Сообщить координатору'});
    expect(send.getAttribute('aria-disabled')).toBe('true');
    await user.click(send);
    expect(apiSpy.mock.calls.some(([path]) => String(path).endsWith('/cancel'))).toBe(false);
    await user.click(screen.getByRole('radio', {name:'Семейные дела'}));
    expect(screen.getByRole('radio', {name:'Семейные дела'}).getAttribute('aria-checked')).toBe('true');
    expect(send.getAttribute('aria-disabled')).toBe('false');
    await user.click(send);
    expect(await screen.findByRole('heading', {name:'Ищем замену'})).toBeTruthy();
    expect(screen.getByText('Координатор видит причину. Место предложим тем, кто в резерве.')).toBeTruthy();
    expect(screen.queryByRole('button', {name:'Всё-таки приду'})).toBeNull();
    const call = apiSpy.mock.calls.find(([path]) => String(path).endsWith('/cancel'))!;
    expect(call[0]).toBe('/api/v1/assignments/paint/cancel');
    expect(call[1]).toMatchObject({body:{expected_version:2, reason:'Не смогу прийти: семейные дела'}});
  });

  it('offers the best event when there are no занятия, says plainly when nothing is planned and explains a pause', async () => {
    feed.items = [card('Арт-суббота', '2026-10-31T11:00:00Z'), card('Шерстяной базар', '2026-11-07T08:00:00Z')];
    view();
    expect(await screen.findByText('Занятий пока нет. Лучше всего подходит тебе')).toBeTruthy();
    expect(screen.getByRole('heading', {level:2, name:'Арт-суббота'})).toBeTruthy();
    expect(screen.getByText('Сб, 31 октября, 14:00–18:00, Грибаново. Нужен ассистент педагога.')).toBeTruthy();
    expect(screen.queryByRole('heading', {name:'Впереди'})).toBeNull();
    expect(within(section('Можно записаться')).getAllByRole('link').map(link => link.getAttribute('href'))).toContain('/events/Шерстяной базар');
    expect(screen.getByRole('link', {name:'Подробнее'}).getAttribute('href')).toBe('/events/Арт-суббота');
    await userEvent.setup().click(screen.getByRole('button', {name:'Записаться'}));
    expect(await screen.findByText('Место за тобой')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Подготовиться'}).getAttribute('href')).toBe('/my/assignments/new/preparation');
    expect(apiSpy.mock.calls.find(([path]) => String(path).endsWith('/sign-up'))![0]).toBe('/api/v1/staffing-needs/need-Арт-суббота/sign-up');
    cleanup();

    feed.items = [];
    view();
    const calm = (await screen.findByRole('heading', {name:'Мероприятия скоро появятся'})).closest('section') as HTMLElement;
    expect(calm.className).toContain('calm');
    expect(within(calm).getByRole('link', {name:'Направления фонда'}).getAttribute('href')).toBe('/opportunities');
    expect(screen.queryByRole('heading', {name:'Можно записаться'})).toBeNull();
    cleanup();

    feed = {algorithm_version:'rules-v3', can_sign_up:false, locked_reason:'volunteer_paused', items:[]};
    view();
    expect(await screen.findByRole('heading', {name:'Участие на паузе'})).toBeTruthy();
    expect(screen.queryByRole('heading', {name:'Нужна пауза?'})).toBeNull();
  }, 15000);

  it('shows own занятия in the month grid and the picked day with its open places', async () => {
    schedule = [
      assignment('paint', 'Живопись с «Подсолнухами»', '2026-10-24T09:00:00Z', {status:'invited', confirmed_at:null, allowed_actions:['confirm','decline']}),
      assignment('fair', 'Ярмарка', '2026-10-18T08:00:00Z', {attendance:{id:'a', version:1, outcome:'attended', minutes:300, ledger_state:'posted'}}),
    ];
    feed.items = [card('Арт-суббота', '2026-10-31T11:00:00Z')];
    reserves = [reserve('felt', 'Мастер-класс по валянию', '2026-10-29T08:00:00Z')];
    view();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('radio', {name:'Календарь'}));
    expect(screen.getByRole('heading', {name:'Октябрь 2026'})).toBeTruthy();
    expect(screen.queryByText('Тебя приглашают')).toBeNull();
    const day = (await screen.findByRole('heading', {name:'Суббота, 24 октября'})).closest('.day-card') as HTMLElement;
    expect(await within(day).findByText('Ждёт ответа')).toBeTruthy();
    expect(within(day).getByText('Живопись с «Подсолнухами»').closest('a')!.getAttribute('href')).toMatch(/^\/my\/assignments\/paint\?/);
    const invited = screen.getByRole('button', {name:'24 октября, занятий: 1'});
    expect(invited.querySelector('.mcal-ev')!.className).toContain('ev-ask');
    expect(invited.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', {name:'18 октября, занятий: 1'}).querySelector('.mcal-ev')!.className).toContain('ev-past');
    expect(screen.getByRole('button', {name:'22 октября'}).getAttribute('aria-current')).toBe('date');
    expect(screen.getByText('Ждут ответа')).toBeTruthy();

    await user.click(screen.getByRole('button', {name:'31 октября'}));
    const other = screen.getByRole('heading', {name:'Суббота, 31 октября'}).closest('.day-card') as HTMLElement;
    expect(within(other).getByText('В этот день занятий нет.')).toBeTruthy();
    expect(within(other).getByText('Арт-суббота').closest('a')!.getAttribute('href')).toBe('/events/Арт-суббота');
    await user.click(screen.getByRole('button', {name:'18 октября, занятий: 1'}));
    expect(screen.getByText('Прошло, часы засчитаны')).toBeTruthy();
    await user.click(screen.getByRole('button', {name:'29 октября, занятий: 1'}));
    const felt = screen.getByRole('heading', {name:'Четверг, 29 октября'}).closest('.day-card') as HTMLElement;
    expect(within(felt).getByText('В резерве')).toBeTruthy();
    expect(within(felt).getByText('Мастер-класс по валянию').closest('a')!.getAttribute('href')).toBe('/events/occ-felt');
    await user.click(screen.getByRole('button', {name:'Следующий месяц'}));
    expect(screen.getByRole('heading', {name:'Ноябрь 2026'})).toBeTruthy();
  }, 15000);
});
