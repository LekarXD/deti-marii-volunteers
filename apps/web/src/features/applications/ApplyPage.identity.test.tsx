// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {ApplyPage} from './ApplyPage';

const state=vi.hoisted(()=>({draft:{} as Record<string,unknown>,api:vi.fn(),submit:vi.fn()}));
vi.mock('../../app/layouts',()=>({useSession:()=>({session:{user_id:'verified-user',verified_email:'verified@example.ru'}})}));
vi.mock('../../api/transport',async()=>({...await vi.importActual('../../api/transport'),api:state.api}));
vi.mock('./api',async()=>({...await vi.importActual('./api'),useDraft:()=>({data:state.draft,isPending:false,error:null}),useApplication:()=>({isPending:false,error:null}),useCommand:()=>({mutateAsync:state.submit,isPending:false,error:null})}));
beforeEach(()=>{
 state.api.mockReset();state.submit.mockReset();
 state.draft={id:'draft-1',version:0,step:0,answers:{email:'stale-form@example.ru',firstName:''},form:{content:{title:'Анкета волонтёра',intro:'',steps:[{title:'Знакомство',fields:[{id:'email',type:'email',label:'Электронная почта',required:true},{id:'firstName',type:'text',label:'Имя',required:true}]}],path:[],shortNames:{}}}};
 state.api.mockImplementation(async(_path:string,{body}:{body:Record<string,unknown>})=>{state.draft={...state.draft,...body,version:1};return state.draft;});state.submit.mockResolvedValue({id:'application-1',version:1});
});
afterEach(cleanup);
function page(){return <QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={['/apply']}><Routes><Route path="/apply" element={<ApplyPage/>}/><Route path="/application" element={<h1>Анкета отправлена</h1>}/></Routes></MemoryRouter></QueryClientProvider>;}

it('replaces stale draft email with server identity and keeps it read-only through submission',async()=>{
 const user=userEvent.setup();render(page());const email=await screen.findByLabelText('Электронная почта *');
 expect((email as HTMLInputElement).value).toBe('verified@example.ru');expect((email as HTMLInputElement).readOnly).toBe(true);
 await user.type(email,'other@example.ru');expect((email as HTMLInputElement).value).toBe('verified@example.ru');
 await user.type(screen.getByLabelText('Имя *'),'Мария');await user.click(screen.getByRole('button',{name:'Отправить анкету'}));await screen.findByRole('heading',{name:'Анкета отправлена'});
 expect(state.submit.mock.calls[0][0].body.answers).toEqual({email:'verified@example.ru',firstName:'Мария'});
});

it('persists the verified email and other draft answers and restores them on page remount',async()=>{
 const user=userEvent.setup();const view=render(page());await user.type(await screen.findByLabelText('Имя *'),'Мария');
 await waitFor(()=>expect(state.api).toHaveBeenCalled(),{timeout:2000});await screen.findByText('Черновик сохранён');
 expect(state.api.mock.calls[0][1].body.answers).toEqual({email:'verified@example.ru',firstName:'Мария'});
 view.unmount();render(page());expect((await screen.findByLabelText('Имя *') as HTMLInputElement).value).toBe('Мария');expect((screen.getByLabelText('Электронная почта *') as HTMLInputElement).value).toBe('verified@example.ru');
});
