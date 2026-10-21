// @vitest-environment jsdom
import {act, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup} from '@testing-library/react';
import {OnboardingPage} from './OnboardingPage';
import {api} from '../../api/transport';

vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'fixture-owner'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const assignment={track_key:'introduction',track_id:'track',id:'assignment',release_id:'release',release_number:1,title:'Fixture',intro:'Fixture',lessons:[{id:'lesson',lesson_id:'stable',key:'history',title:'Fixture module',minutes:1,completed:true}],assessment_version_id:'assessment',completed:true,acknowledged:true,latest_attempt_id:'old',latest_attempt_state:'submitted',reacknowledgement_required:false};
const old={id:'old',assignment_id:'assignment',assessment_version_id:'assessment',state:'submitted',questions:[{id:'question',prompt:'Fixture question',options:['First','Second']}],answers:[{question_id:'question',selected_option:0,correct:true,explanation:'Feedback'}],score:1,total:1};
function mount(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});return render(<QueryClientProvider client={client}><MemoryRouter><OnboardingPage/></MemoryRouter></QueryClientProvider>);}
describe('persistent introduction',()=>{
 it('hides the old result immediately when repeating and loads the new server attempt',async()=>{
  let release:((value:unknown)=>void)|undefined;
  let active=false;
  vi.mocked(api).mockImplementation(async(path)=>{
   if(path==='/api/v1/me/preparation')return {assignments:[{...assignment,latest_attempt_id:active?'new':'old'}],introduction_completed:true,booking_requires_introduction:false} as never;
   if(path==='/api/v1/assessment-attempts/old/result')return old as never;
   if(path==='/api/v1/assessment-attempts/new/result')return {...old,id:'new',state:'active',score:null,answers:[]} as never;
   if(path==='/api/v1/assessments/assessment/attempts')return await new Promise<unknown>(resolve=>{release=resolve;}) as never;
   throw new Error(`Unexpected ${path}`);
  });
  mount();
  await screen.findByText('Правильных ответов: 1 из 1');
  await userEvent.click(screen.getByRole('button',{name:'Пройти тест ещё раз'}));
  expect(screen.queryByText('Правильных ответов: 1 из 1')).toBeNull();
  await waitFor(()=>expect(release).toBeDefined());
  await act(async()=>{active=true;release?.({...old,id:'new',state:'active',score:null,answers:[]});});
  await screen.findByText('Fixture question');
  expect(screen.queryByText('Правильных ответов: 1 из 1')).toBeNull();
  expect(screen.getByRole('button',{name:'First'})).toBeDefined();
 });
});
