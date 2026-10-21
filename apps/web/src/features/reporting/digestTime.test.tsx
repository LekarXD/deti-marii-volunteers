// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {DigestPanel} from './DigestPanel';
const mocks=vi.hoisted(()=>({command:vi.fn().mockResolvedValue({})}));
const scope={scope_type:'foundation' as const,scope_id:null,label:'Фонд',can_write:true,can_export:true};
vi.mock('./api',()=>({scopeQuery:()=>'',dateTime:(v:string)=>v,useReportCommand:()=>({mutateAsync:mocks.command,isPending:false}),useReportQuery:(name:string)=>({data:name==='digest'?{id:'digest',version:3,enabled:false,recipients:[],weekday:0,minute_of_day:600,timezone:'Europe/Moscow',state:'disabled',scope:{scope_type:'foundation',scope_id:null,label:'Фонд',can_write:true},deliveries:[]}:[]})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('rejects invalid raw digest time and saves corrected minutes with the current version',async()=>{const user=userEvent.setup();render(<DigestPanel scope={scope}/>);const time=screen.getByRole('textbox',{name:'Время'});await user.clear(time);await user.type(time,'2575');await user.click(screen.getByRole('button',{name:'Сохранить'}));expect(mocks.command).not.toHaveBeenCalled();expect(document.activeElement).toBe(time);await user.clear(time);await user.type(time,'1500');await user.click(screen.getByRole('button',{name:'Сохранить'}));expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({method:'PUT',body:expect.objectContaining({expected_version:3,minute_of_day:900})}));});
