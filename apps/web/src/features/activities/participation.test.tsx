// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {AssignmentCard} from './Participation';
import type {AssignmentParticipation} from './participationApi';
vi.mock('../../app/layouts/AppProviders',()=>({useSession:()=>({session:{user_id:'volunteer',permissions:[]}})}));
vi.mock('./api',()=>({useActivityCommand:()=>({mutateAsync:vi.fn(),isPending:false,isError:false})}));
afterEach(cleanup);
const item=(changes:Partial<AssignmentParticipation>={}):AssignmentParticipation=>({id:'invite',user_id:'volunteer',display_name:'Тестовый волонтёр',occurrence_id:'event',staffing_need_id:'need',occurrence_status:'scheduled',title:'Подготовка ярмарки',role_title:'Помощь на ярмарке',status:'invited',approved_at:null,confirmed_at:null,starts_at:'2026-10-25T11:00:00Z',ends_at:'2026-10-25T13:00:00Z',timezone:'Europe/Moscow',location:'Мастерская',readiness:[],history:[],allowed_actions:['confirm','decline'],conditions_version:1,points_multiplier:1.5,approval_required:true,version:1,...changes});
it('shows one status line instead of four steps and waits for coordinator approval before confirming',()=>{
 render(<MemoryRouter><AssignmentCard item={item()}/></MemoryRouter>);
 expect(screen.getByText('Координатор ещё не согласовал участие.')).toBeTruthy();expect(screen.getByText('Баллы ×1,5')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Да, я приду'})).toBeNull();expect(screen.queryByText('Согласование')).toBeNull();
 cleanup();render(<MemoryRouter><AssignmentCard item={item({approved_at:'2026-10-22T10:00:00Z'})}/></MemoryRouter>);
 expect(screen.getByText('Координатор согласовал участие. Подтвердите, что придёте.')).toBeTruthy();expect(screen.getByRole('button',{name:'Да, я приду'})).toBeTruthy();
});
