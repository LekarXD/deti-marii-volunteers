// @vitest-environment jsdom
import React,{useState} from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {AppProviders,useSession} from './AppProviders';
import {clearSession} from '../../api/transport';
afterEach(()=>{cleanup();clearSession(false);vi.unstubAllGlobals();});
it('remounts private local form state when verified principal changes',async()=>{
 const base={foundation_id:'f',user_id:null,registration_id:'a',is_staff:false,permissions:[],csrf_token:'a',actor_id:'a',mfa_required:false};
 const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(base))).mockResolvedValueOnce(new Response(JSON.stringify({...base,registration_id:'b',actor_id:'b',csrf_token:'b'})));
 vi.stubGlobal('fetch',fetch);
 function Form(){const [answer,setAnswer]=useState('');const {session,refresh}=useSession();return <><span>{session?.actor_id}</span><input aria-label="Ответ" value={answer} onChange={e=>setAnswer(e.target.value)}/><button onClick={()=>void refresh()}>Другой пользователь</button></>;}
 render(<AppProviders><Form/></AppProviders>);const user=userEvent.setup();await screen.findByLabelText('Ответ');await user.type(screen.getByLabelText('Ответ'),'Частный ответ A');await user.click(screen.getByRole('button',{name:'Другой пользователь'}));await waitFor(()=>expect(screen.getByText('b')).toBeTruthy());expect((screen.getByLabelText('Ответ') as HTMLInputElement).value).toBe('');expect(fetch).toHaveBeenCalledTimes(2);
});
