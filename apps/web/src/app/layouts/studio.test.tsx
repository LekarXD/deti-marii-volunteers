// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {AppProviders} from './AppProviders';
import {StudioLayout,CandidateLayout} from './Layouts';
import {clearSession} from '../../api/transport';
const identity={foundation_id:'f',user_id:'user',registration_id:null,actor_id:'user',mfa_required:false,permissions:[],csrf_token:'csrf'};
afterEach(()=>{cleanup();clearSession(false);vi.unstubAllGlobals();});
function show(is_staff:boolean,path='/studio/current-room'){
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({...identity,is_staff}))));
 render(<MemoryRouter initialEntries={[path]}><AppProviders><Routes><Route element={<StudioLayout/>}><Route path="/studio/:sessionId" element={<h1>Текущее занятие</h1>}/></Route><Route element={<CandidateLayout/>}><Route path="/home" element={<h1>Главная волонтёра</h1>}/></Route></Routes></AppProviders></MemoryRouter>);
}
it('keeps a staff member in the coordinator shell when entering a shared studio route',async()=>{
 show(true);await screen.findByRole('heading',{name:'Текущее занятие'});expect(screen.getByRole('navigation',{name:'Разделы фонда'})).toBeTruthy();expect(screen.queryByRole('navigation',{name:'Разделы волонтёра'})).toBeNull();expect(screen.getByRole('link',{name:'Дети Марии — главная'}).getAttribute('href')).toBe('/fund');expect(screen.getByText('команда фонда')).toBeTruthy();
});
it('keeps an ordinary volunteer in the volunteer shell for the same studio route',async()=>{
 show(false);await screen.findByRole('heading',{name:'Текущее занятие'});expect(screen.getByRole('navigation',{name:'Разделы волонтёра'})).toBeTruthy();expect(screen.queryByRole('navigation',{name:'Разделы фонда'})).toBeNull();expect(screen.getByRole('link',{name:'Дети Марии — главная'}).getAttribute('href')).toBe('/home');expect(screen.getByText('волонтёры «Дети Марии»')).toBeTruthy();
});
it('does not reinterpret the existing home route when a staff principal visits it',async()=>{
 show(true,'/home');await screen.findByRole('heading',{name:'Главная волонтёра'});expect(screen.getByRole('navigation',{name:'Разделы волонтёра'})).toBeTruthy();expect(screen.getByRole('link',{name:'Дети Марии — главная'}).getAttribute('href')).toBe('/home');
});
