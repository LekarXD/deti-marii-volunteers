// @vitest-environment jsdom
import React,{useEffect} from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {AppProviders} from './AppProviders';
import {CandidateLayout} from './Layouts';
import {api,clearSession} from '../../api/transport';
const registration={foundation_id:'f',user_id:null,registration_id:'a',is_staff:false,permissions:[],csrf_token:'a',actor_id:'a',mfa_required:false};
const response=(data:unknown)=>new Response(JSON.stringify(data));
afterEach(()=>{cleanup();clearSession(false);vi.unstubAllGlobals();});
function fixture(){render(<MemoryRouter initialEntries={['/onboarding?view=topics']}><AppProviders><CandidateLayout><p>Материалы знакомства</p></CandidateLayout></AppProviders></MemoryRouter>);}
it('makes sign-in discoverable for registration users with a local next route',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(response(registration)));fixture();const signIn=await screen.findByRole('link',{name:'Войти'});expect(signIn.getAttribute('href')).toBe('/login?next=%2Fonboarding%3Fview%3Dtopics');expect(screen.queryByText('Анна')).toBeNull();expect(screen.getByRole('link',{name:'Дети Марии — главная'}).getAttribute('href')).toBe('/application');expect(screen.queryByRole('link',{name:'Главная'})).toBeNull();});
it('provides verified users cabinet and a real server logout command',async()=>{const fetch=vi.fn().mockResolvedValueOnce(response({...registration,user_id:'verified-user',registration_id:null,actor_id:'verified-user'})).mockResolvedValueOnce(response({status:'ok'})).mockResolvedValueOnce(response(registration));vi.stubGlobal('fetch',fetch);fixture();const user=userEvent.setup();const account=await screen.findByRole('button',{name:'Аккаунт'});expect(screen.getByRole('link',{name:'Дети Марии — главная'}).getAttribute('href')).toBe('/home');expect(screen.getByRole('link',{name:'Главная'}).getAttribute('href')).toBe('/home');await user.click(account);expect(screen.getByRole('link',{name:'Мой кабинет'}).getAttribute('href')).toBe('/');await user.click(screen.getByRole('button',{name:'Выйти'}));await waitFor(()=>expect(fetch.mock.calls.some(([url,options])=>url==='/api/v1/auth/logout'&&options.method==='POST')).toBe(true));await screen.findByRole('link',{name:'Войти'});expect(screen.queryByText('Сессия завершилась. Войдите снова.')).toBeNull();});
it('sends a user whose session ended elsewhere back to sign-in with a return path',async()=>{const sessions=[{...registration,user_id:'verified-user',registration_id:null,actor_id:'verified-user'},registration];let feed=0;vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.endsWith('/auth/session')?response(sessions.shift()??registration):new Response(JSON.stringify({code:++feed===1?'session_expired':'user_required',message:'Войдите снова'}),{status:feed===1?401:403})));function Feed(){useEffect(()=>{void api('/me/events').catch(()=>{});},[]);return <p>Мероприятия</p>;}function Login(){return <p>Вход {useLocation().search}</p>;}
 render(<MemoryRouter initialEntries={['/events?when=weekend']}><AppProviders><Routes><Route path="/events" element={<CandidateLayout><Feed/></CandidateLayout>}/><Route path="/login" element={<Login/>}/></Routes></AppProviders></MemoryRouter>);
 expect(await screen.findByText('Вход ?next=%2Fevents%3Fwhen%3Dweekend')).toBeTruthy();expect(screen.getByText('Сессия завершилась. Войдите снова.')).toBeTruthy();});
