// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {clearSession,initializeSession} from '../../api/transport';
import {NotificationBell,relativeDate,type Inbox} from './NotificationBell';

const session={foundation_id:'f',user_id:'volunteer',registration_id:null,is_staff:false,permissions:[],csrf_token:'csrf',actor_id:'volunteer',mfa_required:false};
const json=(data:unknown)=>new Response(JSON.stringify(data));
const now=Date.now();
const at=(minutes:number)=>new Date(now-minutes*60_000).toISOString();
const kinds=['invitation','place_confirmed','occurrence_cancelled','question_answered','reflection_review','prize_issued','prize_rejected','gratitude','gratitude'] as const;
const items=kinds.map((kind,index)=>({key:`${kind}:${index}`,kind,title:`Заголовок ${index}`,text:`Текст ${index}`,at:at(index+1),href:`/target/${index}`}));

function serve(inbox:Inbox){
 let current=inbox;
 const fetch=vi.fn(async(url:string,options?:RequestInit)=>{
  if(url.endsWith('/auth/session'))return json(session);
  if(url.endsWith('/me/notifications/seen')){current={...current,unread:0};return json(current);}
  if(url.endsWith('/me/notifications'))return json(current);
  return new Response('{}',{status:404});
 });
 vi.stubGlobal('fetch',fetch);return fetch;
}
/** The app renders the shell only after the session is known, so query keys carry the principal from the first render. */
async function mount(){await initializeSession();const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter><p>Снаружи</p><NotificationBell/></MemoryRouter></QueryClientProvider>);}
const seenCalls=(fetch:ReturnType<typeof serve>)=>fetch.mock.calls.filter(([url])=>String(url).endsWith('/me/notifications/seen'));
afterEach(()=>{cleanup();clearSession(false);vi.unstubAllGlobals();vi.useRealTimers();});

describe('NotificationBell',()=>{
 it('shows the orange pip, opens up to eight rows and marks them seen',async()=>{
  const fetch=serve({items,unread:2});await mount();const user=userEvent.setup();
  const bell=await screen.findByRole('button',{name:'Уведомления, есть новые'});
  expect(bell.querySelector('.pip')).not.toBeNull();expect(bell.getAttribute('aria-expanded')).toBe('false');
  await user.click(bell);
  const panel=screen.getByRole('region',{name:'Уведомления'});
  const links=within(panel).getAllByRole('link');expect(links).toHaveLength(8);
  expect(links[0].getAttribute('href')).toBe('/target/0');expect(links[0].textContent).toContain('Заголовок 0');expect(links[0].textContent).toContain('Текст 0');expect(links[0].textContent).toContain('сегодня');
  expect(links[0].className).toContain('is-new');expect(links[1].className).toContain('is-new');expect(links[2].className).not.toContain('is-new');
  expect(panel.querySelector('.bell-ic-y')).not.toBeNull();expect(panel.querySelector('.bell-ic-off')).not.toBeNull();
  await waitFor(()=>expect(seenCalls(fetch)).toHaveLength(1));
  const [,options]=seenCalls(fetch)[0];expect(options?.method).toBe('POST');expect(JSON.parse(String(options?.body))).toEqual({at:items[0].at});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Уведомления'}).querySelector('.pip')).toBeNull());
  expect(screen.getByRole('button',{name:'Уведомления'}).getAttribute('aria-expanded')).toBe('true');
 });
 it('closes on Escape and on a click outside, returning focus to the bell',async()=>{
  serve({items:items.slice(0,1),unread:0});await mount();const user=userEvent.setup();
  const bell=await screen.findByRole('button',{name:'Уведомления'});
  await user.click(bell);expect(screen.getByRole('region',{name:'Уведомления'})).toBeTruthy();
  await user.keyboard('{Escape}');expect(screen.queryByRole('region',{name:'Уведомления'})).toBeNull();expect(document.activeElement).toBe(bell);
  await user.click(bell);expect(screen.getByRole('region',{name:'Уведомления'})).toBeTruthy();
  await user.click(screen.getByText('Снаружи'));expect(screen.queryByRole('region',{name:'Уведомления'})).toBeNull();
 });
 it('says everything is read when there is nothing and does not call seen',async()=>{
  const fetch=serve({items:[],unread:0});await mount();const user=userEvent.setup();
  await user.click(await screen.findByRole('button',{name:'Уведомления'}));
  expect(await screen.findByText('Всё прочитано')).toBeTruthy();expect(seenCalls(fetch)).toHaveLength(0);
 });
 it('asks the server again every minute',async()=>{
  vi.useFakeTimers({shouldAdvanceTime:true});const fetch=serve({items:[],unread:0});await mount();
  await screen.findByRole('button',{name:'Уведомления'});
  const reads=()=>fetch.mock.calls.filter(([url])=>String(url).endsWith('/me/notifications')).length;
  await waitFor(()=>expect(reads()).toBe(1));
  await act(async()=>{await vi.advanceTimersByTimeAsync(30_000);});
  expect(reads()).toBe(1);
  await act(async()=>{await vi.advanceTimersByTimeAsync(31_000);});
  await waitFor(()=>expect(reads()).toBeGreaterThanOrEqual(2));
 });
});

describe('relativeDate',()=>{
 const base=new Date('2026-10-22T12:00:00+03:00');
 it('reads like a person',()=>{
  expect(relativeDate('2026-10-22T09:05:00+03:00',base)).toBe('сегодня, 09:05');
  expect(relativeDate('2026-10-21T23:30:00+03:00',base)).toBe('вчера');
  expect(relativeDate('2026-10-12T10:00:00+03:00',base)).toBe('12 октября');
  expect(relativeDate('2025-12-31T10:00:00+03:00',base)).toBe('31 декабря 2025');
 });
});
