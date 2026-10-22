// @vitest-environment jsdom
import React from 'react';
import {afterEach, beforeEach, describe, expect, it, vi, type MockInstance} from 'vitest';
import {cleanup, render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import * as transport from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {EventsFeedPage, VolunteerEventPage} from './EventsPage';
import {OpportunityPage, VolunteerOpportunitiesPage} from './OpportunitiesPage';

type Card = components['schemas']['VolunteerEventCard'];
type Need = components['schemas']['VolunteerEventNeed'];
type Opportunity = components['schemas']['OpportunityView'];
const need = (changes: Partial<Need> = {}): Need => ({id:'need', version:3, role_id:'role', role_title:'Ассистент педагога', task:'Помогать ведущей.', required:4, confirmed:2, missing:2,
  approval_policy:'self_confirmation', preparation_requirements:[], allowed_actions:['sign-up'], points_multiplier:1, ...changes});
const card = (title: string, changes: Partial<Card> = {}): Card => ({occurrence_id:title, series_id:'series', title, program:'Творческие мастерские', kind:'activity', format:'onsite',
  location:'Грибаново', audience:'Взрослые участники', status:'scheduled', starts_at:'2026-10-31T11:00:00Z', ends_at:'2026-10-31T15:00:00Z', timezone:'Europe/Moscow',
  needs:[need()], best_need_id:'need', reasons:[], full:false, conflict:false, ...changes});
const opportunity = (title: string, changes: Partial<Opportunity> = {}): Opportunity => ({id:title, version:1, title, program:'Творческие мастерские', audience:'Ребята 10–14 лет', task:'Помогать педагогу на занятии.',
  conditions:'', schedule:'Каждую субботу, 14:00–18:00', location:'Москва', format:'onsite', regularity:'regular', approval_policy:'coordinator', state:'published', role_ids:[], allowed_actions:[],
  preparation_requirements:[{key:'intro', title:'Знакомство с фондом', level:'mandatory'}],
  matching:{algorithm_version:'rules-v2', reasons:['Направление «Творчество» из твоей анкеты'], constraints:[], missing_data:['availability'], evidence:[{field:'interests', version:2, source_id:'profile'} as never], context_versions:{profile:3}}, ...changes});
let feed: components['schemas']['VolunteerEventFeed'];
let detail: components['schemas']['VolunteerEventDetail'];
let directions: Opportunity[];
let apiSpy: MockInstance<typeof transport.api>;
const clients: QueryClient[] = [];

beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-22T09:00:00Z'));
  feed = {algorithm_version:'rules-v3', can_sign_up:true, items:[]};
  detail = {...card('Арт-суббота'), algorithm_version:'rules-v3', can_sign_up:true, other_dates:[]};
  directions = [];
  apiSpy = vi.spyOn(transport, 'api').mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.startsWith('/me/events?')) return feed as T;
    if (path.startsWith('/me/events/')) return detail as T;
    if (path.endsWith('/sign-up')) return {id:'assignment', version:1, status:'confirmed'} as T;
    if (path.endsWith('/reserve')) return {id:'reserve', state:'waiting'} as T;
    if (path.endsWith('/cancel')) return {id:'assignment', version:2, status:'cancelled'} as T;
    if (path.endsWith('/confirm') || path.endsWith('/decline')) return {id:'invite', version:6, status:path.endsWith('/confirm') ? 'confirmed' : 'declined'} as T;
    if (path.startsWith('/api/v1/opportunities?')) return {items:directions, next_cursor:null} as T;
    if (path.startsWith('/api/v1/opportunities/')) return directions.find(item => path.endsWith(`/${encodeURIComponent(item.id)}`) || path.endsWith(`/${item.id}`)) as T;
    if (path.startsWith('/me/responses')) return {items:[], next_cursor:null} as T;
    throw new Error(`Unexpected events API: ${path}`);
  });
});
afterEach(() => {cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks();});
function Where() {const location = useLocation(); return <output data-testid="where">{location.pathname}{location.search}</output>;}
function view(path: string) {
  const client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/events" element={<EventsFeedPage/>}/><Route path="/events/:id" element={<VolunteerEventPage/>}/>
    <Route path="/opportunities" element={<VolunteerOpportunitiesPage/>}/><Route path="/opportunities/:id" element={<OpportunityPage/>}/>
  </Routes><Where/></MemoryRouter></QueryClientProvider>);
}

describe('volunteer event feed', () => {
  it('keeps the server order, signs up from the hero in one tap and folds full events away', async () => {
    feed.items = [card('Арт-суббота'), card('Шерстяной Базар', {series_id:'bazaar', starts_at:'2026-11-07T08:00:00Z', ends_at:'2026-11-07T16:00:00Z', needs:[need({missing:1, confirmed:3})]}),
      card('Выезд', {full:true, needs:[need({confirmed:4, missing:0, allowed_actions:['reserve']})]})];
    view('/events');
    expect(await screen.findByText('Лучше всего подходит тебе')).toBeTruthy();
    expect(screen.getByRole('heading', {level:1, name:'Мероприятия'})).toBeTruthy();
    expect(screen.getByRole('navigation', {name:'Мероприятия'})).toBeTruthy();
    expect(screen.getByRole('heading', {level:2, name:'Арт-суббота'})).toBeTruthy();
    expect(screen.getByText('Сб, 31 октября, 14:00–18:00, Грибаново')).toBeTruthy();
    const more = screen.getByRole('heading', {name:'Ещё подходят'}).closest('section') as HTMLElement;
    const tiles = within(more).getAllByRole('link');
    expect(tiles.map(link => link.getAttribute('href'))).toEqual(['/events/Шерстяной Базар']);
    expect(tiles[0].textContent).toContain('Сб, 7 ноября, 11:00');
    expect(tiles[0].textContent).toContain('Осталось одно место');
    expect(screen.queryByText('Выезд')).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', {name:'Показать (1)'}));
    expect(screen.getByRole('heading', {name:'Мест уже нет'})).toBeTruthy();
    expect(screen.getByText('Можно в резерв')).toBeTruthy();
    await userEvent.setup().click(screen.getByRole('button', {name:'Записаться'}));
    expect(await screen.findByText('Место за тобой')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Подготовиться'}).getAttribute('href')).toBe('/my/assignments/assignment/preparation');
    const call = apiSpy.mock.calls.find(([path]) => String(path).endsWith('/sign-up'))!;
    expect(call[0]).toBe('/api/v1/staffing-needs/need/sign-up');
    expect(call[1]).toMatchObject({method:'POST', body:{expected_version:3, message:''}});
    expect(document.body.textContent).not.toMatch(/score|балл|·/i);
  }, 15000);
  it('cancels the fresh sign-up from the hero and returns to the pick', async () => {
    feed.items = [card('Арт-суббота')];
    view('/events');
    await userEvent.setup().click(await screen.findByRole('button', {name:'Записаться'}));
    await userEvent.setup().click(await screen.findByRole('button', {name:'Отменить запись'}));
    expect(await screen.findByText('Лучше всего подходит тебе')).toBeTruthy();
    const call = apiSpy.mock.calls.find(([path]) => String(path).endsWith('/cancel'))!;
    expect(call[0]).toBe('/api/v1/assignments/assignment/cancel');
    expect(call[1]).toMatchObject({method:'POST', body:{expected_version:1, reason:''}});
  });
  it('opens the personal reasons of each card under «Почему так»', async () => {
    feed.items = [card('Арт-суббота', {reasons:['Навык «Рисование» из твоей анкеты', 'Обычно ты приходишь в это время: сб, днём']}), card('Онлайн-афиша', {series_id:'poster', format:'online'}), card('Будничная съёмка', {series_id:'photo', starts_at:'2026-11-05T13:00:00Z', ends_at:'2026-11-05T15:00:00Z', reasons:['Направление «Фото» из твоей анкеты']})];
    view('/events');
    await userEvent.setup().click(await screen.findByRole('button', {name:'Почему так'}));
    const why = document.querySelector('.ev-why') as HTMLElement;
    expect(Array.from(why.querySelectorAll('.ev-why-list > li')).map(item => [item.querySelector('.strong')?.textContent, Array.from(item.querySelectorAll('ul > li')).map(reason => reason.textContent)])).toEqual([
      ['Арт-суббота', ['Навык «Рисование» из твоей анкеты', 'Обычно ты приходишь в это время: сб, днём']],
      ['Будничная съёмка', ['Направление «Фото» из твоей анкеты']]]);
    expect(within(why).queryByText(/Выше то, что подходит тебе/)).toBeNull();
    expect(within(why).getByRole('link', {name:'профиле'}).getAttribute('href')).toBe('/profile');
  });
  it('explains the order in plain words, filters the grid by the chips and shows the points pill', async () => {
    feed.items = [card('Арт-суббота'), card('Онлайн-афиша', {series_id:'poster', format:'online', needs:[need({points_multiplier:1.5, missing:6, required:8})]}), card('Будничная съёмка', {series_id:'photo', starts_at:'2026-11-05T13:00:00Z', ends_at:'2026-11-05T15:00:00Z'})];
    view('/events?when=online');
    const more = (await screen.findByRole('heading', {name:'Ещё подходят'})).closest('section') as HTMLElement;
    expect(screen.getByRole('button', {name:'Онлайн'}).getAttribute('aria-pressed')).toBe('true');
    expect(within(more).getAllByRole('link').map(link => link.querySelector('.h3')?.textContent)).toEqual(['Онлайн-афиша']);
    expect(within(more).getByText('Есть места')).toBeTruthy();
    expect(within(more).getByText('Баллы ×1,5')).toBeTruthy();
    expect(within(more).getByText('Сб, 31 октября, 14:00, онлайн')).toBeTruthy();
    expect(screen.getByRole('heading', {level:2, name:'Арт-суббота'})).toBeTruthy();
    const why = screen.getByRole('button', {name:'Почему так'});
    expect(why.getAttribute('aria-expanded')).toBe('false');
    await userEvent.setup().click(why);
    expect(why.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Выше то, что подходит тебе: навыки и направления из анкеты, удобное время и группы, где ты уже помогаешь. Если места закончились, мероприятие опускается вниз.')).toBeTruthy();
    expect(screen.getByText(/Удобное время можно поменять в/).textContent).toBe('Удобное время можно поменять в профиле.');
    expect(screen.getByRole('link', {name:'профиле'}).getAttribute('href')).toBe('/profile');
    expect(screen.queryByText(/Интересы и время/)).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', {name:'Будни'}));
    expect(screen.getByTestId('where').textContent).toBe('/events?when=weekday');
    expect(within(more).getAllByRole('link').filter(link => link.classList.contains('tile')).map(link => link.querySelector('.h3')?.textContent)).toEqual(['Будничная съёмка']);
  });
  it('shows the calm meeting hero for a newcomer instead of a sign-up button', async () => {
    feed = {algorithm_version:'rules-v3', can_sign_up:false, locked_reason:'meeting_required', locked_message:'Записаться можно после встречи с координатором.', items:[card('Арт-суббота', {needs:[need({allowed_actions:[]})]})]};
    view('/events');
    expect(await screen.findByText('Запись откроется после знакомства')).toBeTruthy();
    expect(screen.getByRole('heading', {name:'Одна встреча с координатором'}).closest('.card-hero')?.classList.contains('calm')).toBe(true);
    expect(screen.getByText('Она нужна один раз, а не перед каждым занятием. После неё можно записываться на любые мероприятия.')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Выбрать время встречи'}).getAttribute('href')).toBe('/interviews');
    expect(screen.queryByRole('button', {name:'Записаться'})).toBeNull();
    expect(screen.getByRole('link', {name:/Арт-суббота/}).getAttribute('href')).toBe('/events/Арт-суббота');
  });
  it('sends a paused volunteer to the profile', async () => {
    feed = {algorithm_version:'rules-v3', can_sign_up:false, locked_reason:'volunteer_paused', locked_message:'Участие сейчас на паузе.', items:[]};
    view('/events');
    expect(await screen.findByRole('link', {name:'Открыть профиль'})).toBeTruthy();
    expect(screen.getByRole('link', {name:'Открыть профиль'}).getAttribute('href')).toBe('/profile');
  });
});

describe('volunteer event page', () => {
  it('offers the reserve for a full role and lets the volunteer pick another role', async () => {
    detail = {...detail, full:false, needs:[need({confirmed:4, missing:0, allowed_actions:['reserve']}), need({id:'escort', role_title:'Сопровождающий в дороге', approval_policy:'coordinator', required:2, confirmed:1, missing:1, points_multiplier:1.5})],
      reasons:['Направление «Творчество» из твоей анкеты'], contacts:[{role:'Ведущий', display_name:'Елена Петрова'}, {role:'Координатор', display_name:'Мария'}], other_dates:[{occurrence_id:'next', starts_at:'2026-11-07T11:00:00Z', ends_at:'2026-11-07T15:00:00Z', full:false, mine:false}]};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Все места заняты')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Все мероприятия'}).getAttribute('href')).toBe('/events');
    expect(screen.getByRole('heading', {level:2, name:'Сб, 31 октября, 14:00'})).toBeTruthy();
    expect(screen.getByText('До 18:00, Грибаново')).toBeTruthy();
    expect((screen.getByText('Все места заняты').closest('.card-hero') as HTMLElement).style.background).toMatch(/tint/);
    await userEvent.setup().click(screen.getByRole('button', {name:'Встать в резерв'}));
    expect(apiSpy.mock.calls.some(([path, options]) => path === '/api/v1/staffing-needs/need/reserve' && (options as {body?:unknown})?.body !== undefined)).toBe(true);
    const escort = screen.getByRole('button', {name:/Сопровождающий в дороге/});
    expect(within(escort).getByText('Баллы ×1,5')).toBeTruthy();
    expect(within(escort).getByText('Осталось одно место')).toBeTruthy();
    await userEvent.setup().click(escort);
    expect(escort.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('Есть места')).toBeTruthy();
    expect(screen.getByRole('button', {name:'Записаться: сопровождающий в дороге'})).toBeTruthy();
    expect(screen.queryByText(/Участие подтверждает координатор/)).toBeNull();
    expect(screen.getByRole('link', {name:'Сб, 7 ноября'}).getAttribute('href')).toBe('/events/next');
    expect(screen.getByRole('heading', {name:'Кого ждём'})).toBeTruthy();
    const team = screen.getByRole('heading', {name:'Команда'}).closest('.card') as HTMLElement;
    expect(within(team).getByText('Елена, ведущий')).toBeTruthy();
    expect(within(team).getByText('ЕП')).toBeTruthy();
    expect(within(team).getByText('Мария, координатор')).toBeTruthy();
    expect(screen.queryByText('Почему тебе подходит')).toBeNull();
    expect(screen.queryByText('Направление «Творчество» из твоей анкеты')).toBeNull();
  });
  it('shows the waiting position and a way out of the reserve', async () => {
    detail = {...detail, needs:[need({confirmed:4, missing:0, allowed_actions:[]})], my_reserve:{id:'reserve', version:2, occurrence_id:'Арт-суббота', staffing_need_id:'need', state:'waiting', position:2,
      offered_assignment_id:null, queued_at:'2026-10-22T08:00:00Z', allowed_actions:['leave']}};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Ты в резерве')).toBeTruthy();
    expect(screen.getByText('Место в резерве: 2. Если освободится, напишем, а участие подтвердит координатор.')).toBeTruthy();
    await userEvent.setup().click(screen.getByRole('button', {name:'Выйти из резерва'}));
    expect(apiSpy.mock.calls.some(([path, options]) => path === '/api/v1/reserves/reserve/leave' && (options as {body?:{expected_version?:number}})?.body?.expected_version === 2)).toBe(true);
  });
  it('lets the volunteer answer a coordinator invitation right on the event page', async () => {
    detail = {...detail, my_assignment:{id:'invite', version:5, staffing_need_id:'need', status:'invited', origin:'invitation', approved_at:null, awaiting_coordinator:false}, needs:[need({allowed_actions:[]})]};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Тебя приглашают')).toBeTruthy();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', {name:'Не смогу'}));
    expect(screen.getByText('Не сможешь прийти?')).toBeTruthy();
    const send = screen.getByRole('button', {name:'Сообщить координатору'});
    expect(send.getAttribute('aria-disabled')).toBe('true');
    await user.click(within(screen.getByRole('radiogroup', {name:'Почему не получится'})).getByRole('radio', {name:'Работа'}));
    await user.click(send);
    expect(apiSpy.mock.calls.some(([path, options]) => path === '/api/v1/assignments/invite/decline' && JSON.stringify((options as {body?:unknown}).body) === JSON.stringify({expected_version:5, reason:'Не смогу прийти: работа'}))).toBe(true);
    cleanup();
    view('/events/Арт-суббота');
    await user.click(await screen.findByRole('button', {name:'Я приду'}));
    expect(apiSpy.mock.calls.some(([path, options]) => path === '/api/v1/assignments/invite/confirm' && (options as {body?:{expected_version?:number}}).body?.expected_version === 5)).toBe(true);
  });
  it('shows a self sign-up and a freed reserve place as waiting for the coordinator, with a way out', async () => {
    detail = {...detail, my_assignment:{id:'mine', version:2, staffing_need_id:'need', status:'invited', origin:'self', approved_at:null, awaiting_coordinator:true}, needs:[need({allowed_actions:[]})]};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Ждёт ответа координатора')).toBeTruthy();
    expect(screen.getByRole('button', {name:'Отменить заявку'})).toBeTruthy();
    expect(screen.queryByRole('button', {name:'Я приду'})).toBeNull();
    cleanup();
    detail = {...detail, my_assignment:{id:'mine', version:2, staffing_need_id:'need', status:'invited', origin:'reserve', approved_at:null}};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Освободилось место из резерва')).toBeTruthy();
    expect(screen.getByText('Координатор подтвердит участие.')).toBeTruthy();
    expect(screen.getByRole('button', {name:'Не смогу'})).toBeTruthy();
    expect(screen.queryByText('Место за тобой')).toBeNull();
  });
  it('lets a signed-up volunteer prepare or cancel and marks done preparation', async () => {
    detail = {...detail, my_assignment:{id:'assignment', version:4, staffing_need_id:'need', status:'confirmed', origin:'self', approved_at:null},
      needs:[need({allowed_actions:[], preparation_requirements:[{key:'intro', title:'Знакомство с фондом', level:'mandatory'}, {key:'book', title:'Медицинская книжка', level:'recommended'}],
        readiness:[{key:'intro', title:'Знакомство с фондом', level:'mandatory', state:'fulfilled'}, {key:'book', title:'Медицинская книжка', level:'recommended', state:'pending'}]})]};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Место за тобой')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Подготовиться'}).getAttribute('href')).toBe('/my/assignments/assignment/preparation');
    expect(screen.getByText('Готово:').parentElement?.textContent).toBe('Готово: Знакомство с фондом');
    const book = screen.getByText('Медицинская книжка, по желанию').closest('.rowi') as HTMLElement;
    expect(book.querySelector('.st')?.className).toBe('st st-off');
    expect(screen.queryByRole('heading', {name:'Команда'})).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', {name:'Отменить запись'}));
    expect(apiSpy.mock.calls.some(([path, options]) => path === '/api/v1/assignments/assignment/cancel' && (options as {body?:{expected_version?:number}})?.body?.expected_version === 4)).toBe(true);
  });
});

describe('volunteer directions', () => {
  it('lists the directions under the events tabs with search and chips, no hero', async () => {
    directions = [opportunity('Ассистент педагога'), opportunity('Видеомонтаж', {format:'online', schedule:'', regularity:'tasks'})];
    view('/opportunities');
    expect(await screen.findByRole('heading', {name:'Ассистент педагога'})).toBeTruthy();
    expect(screen.getByRole('heading', {level:1, name:'Мероприятия'})).toBeTruthy();
    expect(screen.getByRole('navigation', {name:'Мероприятия'})).toBeTruthy();
    expect(document.querySelector('.card-hero')).toBeNull();
    expect(screen.getByText('Каждую субботу, 14:00–18:00')).toBeTruthy();
    expect(screen.getByText('По задачам')).toBeTruthy();
    expect(screen.getByRole('link', {name:'Подробнее: Ассистент педагога'}).getAttribute('href')).toBe('/opportunities/Ассистент педагога');
    await userEvent.setup().click(screen.getByRole('button', {name:'Онлайн'}));
    expect(screen.getByTestId('where').textContent).toBe('/opportunities?filter=online');
    expect(apiSpy.mock.calls.some(([path]) => String(path).includes('format=online'))).toBe(true);
    await userEvent.setup().type(screen.getByRole('searchbox', {name:'Поиск направления'}), 'фото');
    expect(apiSpy.mock.calls.some(([path]) => String(path).includes('q=%D1%84%D0%BE%D1%82%D0%BE'))).toBe(true);
  });
  it('shows a direction in the tile language without the technical explanation', async () => {
    directions = [opportunity('Ассистент педагога')];
    view('/opportunities/Ассистент педагога?return=filter%3Donline');
    expect(await screen.findByRole('heading', {level:1, name:'Ассистент педагога'})).toBeTruthy();
    expect(screen.getByRole('link', {name:'Направления фонда'}).getAttribute('href')).toBe('/opportunities?filter=online');
    expect(screen.getByRole('heading', {name:'Каждую субботу, 14:00–18:00'})).toBeTruthy();
    expect(screen.getByText('Знакомство с фондом')).toBeTruthy();
    expect(screen.getByText('Участие согласует координатор.')).toBeTruthy();
    expect(screen.getByText('Направление «Творчество» из твоей анкеты')).toBeTruthy();
    expect(screen.queryByText('Источники объяснения')).toBeNull();
    expect(screen.queryByText('Что ещё не проверено')).toBeNull();
    expect(document.body.textContent).not.toMatch(/версия/i);
  });
});
