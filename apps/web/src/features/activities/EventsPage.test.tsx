// @vitest-environment jsdom
import React from 'react';
import {afterEach, beforeEach, describe, expect, it, vi, type MockInstance} from 'vitest';
import {cleanup, render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import * as transport from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {EventsFeedPage, VolunteerEventPage} from './EventsPage';

type Card = components['schemas']['VolunteerEventCard'];
type Need = components['schemas']['VolunteerEventNeed'];
const need = (changes: Partial<Need> = {}): Need => ({id:'need', version:3, role_id:'role', role_title:'Ассистент педагога', task:'Помогать ведущей.', required:4, confirmed:2, missing:2,
  approval_policy:'self_confirmation', preparation_requirements:[], allowed_actions:['sign-up'], ...changes});
const card = (title: string, changes: Partial<Card> = {}): Card => ({occurrence_id:title, series_id:'series', title, program:'Творческие мастерские', kind:'activity', format:'onsite',
  location:'Грибаново', audience:'Взрослые участники', status:'scheduled', starts_at:'2026-10-31T11:00:00Z', ends_at:'2026-10-31T15:00:00Z', timezone:'Europe/Moscow',
  needs:[need()], best_need_id:'need', reasons:[], full:false, conflict:false, ...changes});
let feed: components['schemas']['VolunteerEventFeed'];
let detail: components['schemas']['VolunteerEventDetail'];
let apiSpy: MockInstance<typeof transport.api>;
const clients: QueryClient[] = [];

beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-22T09:00:00Z'));
  feed = {algorithm_version:'rules-v3', can_sign_up:true, items:[]};
  detail = {...card('Арт-суббота'), algorithm_version:'rules-v3', can_sign_up:true, other_dates:[]};
  apiSpy = vi.spyOn(transport, 'api').mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.startsWith('/me/events?')) return feed as T;
    if (path.startsWith('/me/events/')) return detail as T;
    if (path.endsWith('/sign-up')) return {id:'assignment', status:'confirmed'} as T;
    if (path.endsWith('/reserve')) return {id:'reserve', state:'waiting'} as T;
    throw new Error(`Unexpected events API: ${path}`);
  });
});
afterEach(() => {cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks();});
function view(path: string) {
  const client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/events" element={<EventsFeedPage/>}/><Route path="/events/:id" element={<VolunteerEventPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
}

describe('volunteer event feed', () => {
  it('keeps the server order, signs up from the hero in one tap and moves full events to the end', async () => {
    feed.items = [card('Арт-суббота'), card('Шерстяной Базар', {starts_at:'2026-11-07T08:00:00Z', ends_at:'2026-11-07T16:00:00Z'}), card('Выезд', {full:true, needs:[need({confirmed:4, missing:0, allowed_actions:['reserve']})]})];
    view('/events');
    expect(await screen.findByText('Лучше всего подходит тебе')).toBeTruthy();
    expect(screen.getByRole('heading', {level:2, name:'Арт-суббота'})).toBeTruthy();
    expect(screen.getByText('Ассистент педагога: записались 2 из 4')).toBeTruthy();
    const more = screen.getByRole('heading', {name:'Ещё подходят'}).closest('section') as HTMLElement;
    expect(within(more).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual(['/events/Шерстяной Базар']);
    await userEvent.setup().click(screen.getByRole('button', {name:'Показать (1)'}));
    expect(screen.getByText('Записались 4 из 4, можно в резерв')).toBeTruthy();
    await userEvent.setup().click(screen.getByRole('button', {name:'Записаться'}));
    expect(await screen.findByText('Место за тобой')).toBeTruthy();
    const call = apiSpy.mock.calls.find(([path]) => String(path).endsWith('/sign-up'))!;
    expect(call[0]).toBe('/api/v1/staffing-needs/need/sign-up');
    expect(call[1]).toMatchObject({method:'POST', body:{expected_version:3, message:''}});
    expect(document.body.textContent).not.toMatch(/score|балл/i);
  });
  it('shows the locked path for a newcomer instead of a sign-up button', async () => {
    feed = {algorithm_version:'rules-v3', can_sign_up:false, locked_reason:'meeting_required', locked_message:'Записаться можно после встречи с координатором.', items:[card('Арт-суббота', {needs:[need({allowed_actions:[]})]})]};
    view('/events');
    expect(await screen.findByRole('heading', {name:'Записаться можно после встречи с координатором.'})).toBeTruthy();
    expect(screen.getByRole('link', {name:'Встреча с координатором'}).getAttribute('href')).toBe('/interviews');
    expect(screen.queryByRole('button', {name:'Записаться'})).toBeNull();
    expect(screen.getByRole('link', {name:/Арт-суббота/}).getAttribute('href')).toBe('/events/Арт-суббота');
  });
});

describe('volunteer event page', () => {
  it('offers the reserve for a full role and lets the volunteer pick another role', async () => {
    detail = {...detail, full:false, needs:[need({confirmed:4, missing:0, allowed_actions:['reserve']}), need({id:'escort', role_title:'Сопровождающий в дороге', approval_policy:'coordinator', required:2, confirmed:1, missing:1})],
      reasons:['Направление «Творчество» из твоей анкеты'], other_dates:[{occurrence_id:'next', starts_at:'2026-11-07T11:00:00Z', ends_at:'2026-11-07T15:00:00Z', full:false, mine:false}]};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Все места заняты')).toBeTruthy();
    await userEvent.setup().click(screen.getByRole('button', {name:'Встать в резерв'}));
    expect(apiSpy.mock.calls.some(([path, options]) => path === '/api/v1/staffing-needs/need/reserve' && (options as {body?:unknown})?.body !== undefined)).toBe(true);
    await userEvent.setup().click(screen.getByRole('button', {name:/Сопровождающий в дороге/}));
    expect(screen.getByText('Есть места')).toBeTruthy();
    expect(screen.getByText(/Участие подтверждает координатор/)).toBeTruthy();
    expect(screen.getByRole('link', {name:'Сб, 7 ноября'}).getAttribute('href')).toBe('/events/next');
    expect(screen.getByText('Направление «Творчество» из твоей анкеты')).toBeTruthy();
  });
  it('shows the waiting position and a way out of the reserve', async () => {
    detail = {...detail, needs:[need({confirmed:4, missing:0, allowed_actions:[]})], my_reserve:{id:'reserve', version:2, occurrence_id:'Арт-суббота', staffing_need_id:'need', state:'waiting', position:2,
      offered_assignment_id:null, queued_at:'2026-10-22T08:00:00Z', allowed_actions:['leave']}};
    view('/events/Арт-суббота');
    expect(await screen.findByText('Ты в резерве')).toBeTruthy();
    expect(screen.getByText('Ты 2-й в резерве. Напишем, если место освободится.')).toBeTruthy();
    expect(screen.getByRole('button', {name:'Выйти из резерва'})).toBeTruthy();
  });
});
