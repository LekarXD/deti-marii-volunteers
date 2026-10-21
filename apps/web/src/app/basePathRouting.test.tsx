// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Routes,Route,Link,useNavigate,useLocation} from 'react-router-dom';
import {getAppBasePath} from '../basePath';
afterEach(()=>{cleanup();vi.unstubAllEnvs();});
function Login(){const navigate=useNavigate();return <button onClick={()=>navigate('/fund/groups?tab=current')}>Вернуться к работе</button>;}
function Groups(){const location=useLocation();return <><Link to="/login">Войти</Link><output>{location.pathname+location.search}</output></>;}
it.each(['/','/deti-marii'])('keeps a deep-linked SPA page, links and login return inside %s',async(mount)=>{
 vi.stubEnv('VITE_APP_BASE_PATH',mount);const prefix=mount==='/'?'':mount;
 render(<MemoryRouter basename={getAppBasePath()||'/'} initialEntries={[`${prefix}/fund/groups?tab=current`]}><Routes><Route path="/fund/groups" element={<Groups/>}/><Route path="/login" element={<Login/>}/></Routes></MemoryRouter>);
 expect(screen.getByRole('link',{name:'Войти'}).getAttribute('href')).toBe(`${prefix}/login`);const user=userEvent.setup();await user.click(screen.getByRole('link',{name:'Войти'}));await user.click(await screen.findByRole('button',{name:'Вернуться к работе'}));expect(await screen.findByText('/fund/groups?tab=current')).toBeTruthy();expect(screen.getByRole('link',{name:'Войти'}).getAttribute('href')).toBe(`${prefix}/login`);
});
