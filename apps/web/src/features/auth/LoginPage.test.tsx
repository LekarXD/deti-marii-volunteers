// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {LoginPage,safeReturnPath} from './LoginPage';

const state=vi.hoisted(()=>({
  session:{user_id:null as string|null,registration_id:'anonymous' as string|null,foundation_id:'foundation',is_staff:false,mfa_required:false,permissions:[] as string[],csrf_token:'csrf'},
  api:vi.fn(),refresh:vi.fn(),logout:vi.fn(),
}));
vi.mock('../../api/transport',()=>({api:state.api}));
vi.mock('../../app/layouts',()=>({useSession:()=>({session:state.session,refresh:state.refresh,logout:state.logout})}));
function Location(){const location=useLocation();return <output data-testid="location">{location.pathname}{location.search}</output>;}
function tree(path='/login?next=%2Ffund%2Fgroups'){return <MemoryRouter initialEntries={[path]}><Routes><Route path="/login" element={<LoginPage/>}/><Route path="/fund/groups" element={<h1>Groups destination</h1>}/><Route path="/application" element={<h1>Application destination</h1>}/></Routes><Location/></MemoryRouter>;}
beforeEach(()=>{state.api.mockReset();state.refresh.mockReset();state.logout.mockReset();state.session={user_id:null,registration_id:'anonymous' as string|null,foundation_id:'foundation',is_staff:false,mfa_required:false,permissions:[],csrf_token:'csrf'};});
afterEach(cleanup);

describe('safe return navigation',()=>{
  it.each(['https://evil.test','//evil.test','/\\evil.test','/%2f%2fevil.test','/login?next=/fund','/api/v1/auth/session','/bad\npath'])( 'rejects %s',path=>{expect(safeReturnPath(path)).toBe('/application');});
  it('keeps a same-app destination',()=>{expect(safeReturnPath('/fund/groups?tab=current#members')).toBe('/fund/groups?tab=current#members');});
});

describe('authentication stages',()=>{
  it('never consumes a link on GET, then remounts into MFA after a principal-changing refresh',async()=>{
    const user=userEvent.setup();
    const secret='a-secret-token-with-at-least-twenty-characters';
    const path=`/login?next=%2Ffund%2Fgroups&challenge_id=123e4567-e89b-42d3-a456-426614174000&token=${secret}`;
    const ui=tree(path);const view=render(ui);
    await waitFor(()=>expect(screen.getByTestId('location').textContent).toBe('/login?next=%2Ffund%2Fgroups'));
    expect(state.api).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain(secret);
    state.api.mockImplementation(async(path:string)=>path==='/auth/challenges/verify'?{...state.session,user_id:'staff-user',mfa_required:true}:{...state.session,is_staff:true,mfa_required:false,recovery_codes:[]});
    state.refresh.mockImplementation(async()=>{state.session=state.session.user_id?{...state.session,is_staff:true,mfa_required:false}:{...state.session,user_id:'staff-user',registration_id:null,mfa_required:true};view.rerender(ui);return state.session;});
    await user.click(screen.getByRole('button',{name:'Подтвердить вход'}));
    await screen.findByRole('heading',{name:'Подтвердите вход'});
    expect(screen.queryByRole('heading',{name:'Groups destination'})).toBeNull();
    await user.type(screen.getByLabelText('Код из приложения'),'123456');
    await user.click(screen.getByRole('button',{name:'Подтвердить вход'}));
    await screen.findByRole('heading',{name:'Groups destination'});
    expect(state.api).toHaveBeenNthCalledWith(1,'/auth/challenges/verify',{method:'POST',body:{challenge_id:'123e4567-e89b-42d3-a456-426614174000',token:secret}});
    expect(state.api).toHaveBeenNthCalledWith(2,'/auth/mfa/verify',{method:'POST',body:{code:'123456'}});
  });

  it('reports queued dev delivery without claiming a sent email or reading a secret',async()=>{
    const user=userEvent.setup();
    state.api.mockResolvedValue({challenge_id:'123e4567-e89b-42d3-a456-426614174000',status:'queued',delivery:'dev_inbox'});
    render(tree());await user.type(screen.getByLabelText('Электронная почта'),'person@example.ru');await user.click(screen.getByRole('button',{name:'Получить ссылку для входа'}));
    expect(await screen.findByText('Запрос на вход поставлен в очередь.')).toBeTruthy();
    expect(screen.getByText('Запрос на вход поставлен в очередь.')).toBeTruthy();
    expect(screen.getByText(/В тестовой установке письмо не отправляется/)).toBeTruthy();
    expect(state.api).toHaveBeenCalledExactlyOnceWith('/auth/challenges',{method:'POST',body:{email:'person@example.ru',purpose:'login'}});
    expect(screen.getByLabelText('Код подтверждения из письма').getAttribute('type')).toBe('password');
  });

  it('uses an existing recovery code through the real MFA command, without a reset flow',async()=>{
    const user=userEvent.setup();state.session={...state.session,user_id:'staff-user',mfa_required:true};
    const ui=tree();const view=render(ui);
    state.api.mockResolvedValue({...state.session,is_staff:true,mfa_required:false,recovery_codes:[]});
    state.refresh.mockImplementation(async()=>{state.session={...state.session,is_staff:true,mfa_required:false};view.rerender(ui);return state.session;});
    await user.click(screen.getByRole('radio',{name:'Код восстановления'}));
    await user.type(screen.getByLabelText('Одноразовый код восстановления'),'abcdef1234567890');
    await user.click(screen.getByRole('button',{name:'Подтвердить вход'}));
    await screen.findByRole('heading',{name:'Groups destination'});
    expect(state.api).toHaveBeenCalledExactlyOnceWith('/auth/mfa/verify',{method:'POST',body:{code:'abcdef1234567890'}});
  });
});
