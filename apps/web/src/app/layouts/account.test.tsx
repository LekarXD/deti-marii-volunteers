// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {AppProviders} from './AppProviders';
import {CandidateLayout} from './Layouts';
import {clearSession} from '../../api/transport';
const registration={foundation_id:'f',user_id:null,registration_id:'a',is_staff:false,permissions:[],csrf_token:'a',actor_id:'a',mfa_required:false};
const response=(data:unknown)=>new Response(JSON.stringify(data));
afterEach(()=>{cleanup();clearSession(false);vi.unstubAllGlobals();});
function fixture(){render(<MemoryRouter initialEntries={['/onboarding?view=topics']}><AppProviders><CandidateLayout><p>Материалы знакомства</p></CandidateLayout></AppProviders></MemoryRouter>);}
it('makes sign-in discoverable for registration users with a local next route',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(response(registration)));fixture();const signIn=await screen.findByRole('link',{name:'Войти'});expect(signIn.getAttribute('href')).toBe('/login?next=%2Fonboarding%3Fview%3Dtopics');expect(screen.queryByText('Анна')).toBeNull();});
it('provides verified users cabinet and a real server logout command',async()=>{const fetch=vi.fn().mockResolvedValueOnce(response({...registration,user_id:'verified-user',registration_id:null,actor_id:'verified-user'})).mockResolvedValueOnce(response({status:'ok'})).mockResolvedValueOnce(response(registration));vi.stubGlobal('fetch',fetch);fixture();const user=userEvent.setup();await user.click(await screen.findByRole('button',{name:'Аккаунт'}));expect(screen.getByRole('link',{name:'Мой кабинет'}).getAttribute('href')).toBe('/application');await user.click(screen.getByRole('button',{name:'Выйти'}));await waitFor(()=>expect(fetch.mock.calls.some(([url,options])=>url==='/api/v1/auth/logout'&&options.method==='POST')).toBe(true));await screen.findByRole('link',{name:'Войти'});});
