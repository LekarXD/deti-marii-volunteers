// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {api,type ApiOptions} from '../../api/transport';
import type {Task,Volunteer} from './api';
import {VolunteerRecordPage} from './VolunteerRecordPage';
vi.mock('../../api/transport',async load=>({...await load<typeof import('../../api/transport')>(),api:vi.fn(),getSession:()=>({permissions:['crm.write'],user_id:'staff-1'})}));
const task:Task={id:'task-1',volunteer_id:'vol-1',application_id:null,assigned_user_id:'staff-1',due_on:'2026-10-25',title:'Позвонить волонтёру',state:'open',version:1,source_type:'manual',source_id:'source-1',source_revision:1,completed_at:null};
const fixture:Volunteer={id:'vol-1',version:5,display_name:'Анна Учебная',agreements:[],application_id:null,availability:null,blocked_reasons:[],can_invite:false,trusted_with_newcomers:false,contact_events:[],contacts:{},context:'',follow_up_tasks:[task],import_provenance:[],latest_reflection:null,merged_into_id:null,merged_record_ids:[],next_task:task,no_contact:false,relationship_state:'contacted',reviews:[]};
let current:Volunteer,foreign=0;const clients:QueryClient[]=[];
beforeEach(()=>{current=structuredClone(fixture);foreign=0;vi.mocked(api).mockImplementation(async<T,>(path:string,options?:ApiOptions):Promise<T>=>{
 if(path==='/coord/volunteers/vol-1')return current as T;
 if(path==='/coord/follow-up-tasks/task-1'){const closed={...task,state:'done',version:2};current={...current,version:current.version+foreign+1,next_task:null,follow_up_tasks:[closed]};return closed as T;}
 if(path==='/coord/volunteers/vol-1/agreements')return {...current,version:(options?.body as {expected_version:number}).expected_version+1} as T;
 throw new Error('Unexpected CRM API '+path);
});});
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.clearAllMocks();});
function view(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/volunteers/vol-1']}><Routes><Route path="/fund/volunteers/:id" element={<VolunteerRecordPage/>}/></Routes></MemoryRouter></QueryClientProvider>);}
async function completeNextStepThenSave(){
 const user=userEvent.setup();view();await user.type(await screen.findByLabelText('О чём договорились'),'Готова помогать по субботам');
 await user.click(screen.getByRole('button',{name:'Отметить выполненным'}));await screen.findByText('Следующий шаг не назначен');
 await user.click(screen.getByRole('button',{name:'Сохранить договорённость'}));
 await waitFor(()=>expect(vi.mocked(api).mock.calls.some(([path])=>path==='/coord/volunteers/vol-1/agreements')).toBe(true));
 return vi.mocked(api).mock.calls.find(([path])=>path==='/coord/volunteers/vol-1/agreements')![1]!.body as {expected_version:number;text:string};
}
it('keeps typed agreement savable after completing the next step on the same card',async()=>{
 const body=await completeNextStepThenSave();expect(body).toMatchObject({expected_version:6,text:'Готова помогать по субботам'});expect(screen.queryByRole('alert')).toBeNull();
});
it('follows only its own write, so a change by someone else still reaches the version check',async()=>{
 foreign=1;const body=await completeNextStepThenSave();expect(current.version).toBe(7);expect(body.expected_version).toBe(6);
});
