// @vitest-environment jsdom
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {CandidatesPage} from './CandidatesPage';
import {useCandidate,useCandidates,useCandidateSummary,useCommand,type Candidate,type CandidateSummary} from './api';

vi.mock('./api',()=>({useCandidates:vi.fn(),useCandidate:vi.fn(),useCandidateSummary:vi.fn(),useCommand:vi.fn(),useDraft:vi.fn(),useNotes:vi.fn(),useRequests:vi.fn()}));
vi.mock('../../api/transport',async original=>({...await original<typeof import('../../api/transport')>(),getSession:()=>({user_id:'me',permissions:['candidates.read','candidates.review']})}));

const day=86400000;
const ago=(days:number)=>new Date(Date.now()-days*day-3600000).toISOString();
function person(id:string,first:string,stage:Candidate['stage'],extra:Partial<Candidate>={},answers:Record<string,unknown>={}):Candidate{
  return {id,version:2,submission_state:'submitted',review_state:stage==='new'?'new':'reviewing',submitted_at:ago(1),stage,stage_since:null,assigned_coordinator_id:null,history:[],consents:{},revisions:[],
    revision:{id:`${id}-r`,number:1,form_version_id:'f',created_at:ago(1),answers:{firstName:first,lastName:'Тестова',directions:['Ярмарки'],participation:'Каждую неделю',telegram:'@'+id,...answers}},
    progress:{introduction:{status:'not_started',completed_lessons:0,total_lessons:4},interview:{status:'none',starts_at:null,booking_id:null}},...extra} as Candidate;
}
const stale=person('polina','Полина','new',{submitted_at:ago(3)},{volExpText:'Продавала на маркетах'});
const fresh=person('elena','Елена','new',{submitted_at:ago(0)});
const learning=person('anna','Анна','intro',{progress:{introduction:{status:'in_progress',completed_lessons:1,total_lessons:4},interview:{status:'none',starts_at:null,booking_id:null}}});
const waiting=person('maria','Мария','interview',{progress:{introduction:{status:'completed',completed_lessons:4,total_lessons:4},interview:{status:'none',starts_at:null,booking_id:null}}});
const booked=person('timur','Тимур','interview',{progress:{introduction:{status:'completed',completed_lessons:4,total_lessons:4},interview:{status:'booked',starts_at:'2026-10-23T07:00:00Z',booking_id:'booking-1'}}});
const ready=person('sergey','Сергей','ready',{stage_since:'2026-10-21T09:00:00Z',progress:{introduction:{status:'completed',completed_lessons:4,total_lessons:4},interview:{status:'completed',starts_at:'2026-10-21T09:00:00Z',booking_id:'booking-0'}}});
const many=Array.from({length:6},(_,index)=>person(`ready-${index}`,`Готов${index}`,'ready'));
let lists:Record<string,Candidate[]>;
let summary:CandidateSummary;
const commands:Record<string,{mutateAsync:ReturnType<typeof vi.fn>;isPending:boolean;error:null}>={};

function Where(){const location=useLocation();return <output data-testid="where">{location.pathname+location.search}</output>;}
function page(entry='/fund/candidates'){render(<MemoryRouter initialEntries={[entry]}><Routes><Route path="/fund/candidates" element={<><CandidatesPage/><Where/></>}/><Route path="*" element={<Where/>}/></Routes></MemoryRouter>);}
const stageOf=(title:string)=>screen.getByRole('region',{name:title});

beforeEach(()=>{
  lists={new:[stale,fresh],intro:[learning],interview:[waiting,booked],ready:[ready],closed:[]};
  summary={new:2,intro:1,interview:2,ready:1,done:4,closed:0};
  vi.mocked(useCandidateSummary).mockImplementation(()=>({data:summary,isPending:false,error:null}) as unknown as ReturnType<typeof useCandidateSummary>);
  vi.mocked(useCandidates).mockImplementation(query=>{const params=new URLSearchParams(query),rows=lists[params.get('stage')||'']??[],limit=Number(params.get('limit')||30);return {data:{items:rows.slice(0,limit),total:rows.length,offset:0,limit},isPending:false,error:null} as unknown as ReturnType<typeof useCandidates>;});
  vi.mocked(useCandidate).mockImplementation((id,seed)=>({data:seed??Object.values(lists).flat().find(item=>item.id===id),isPending:false,error:null}) as unknown as ReturnType<typeof useCandidate>);
  vi.mocked(useCommand).mockImplementation(path=>(commands[path]??={mutateAsync:vi.fn().mockResolvedValue({}),isPending:false,error:null}) as unknown as ReturnType<typeof useCommand>);
});
afterEach(()=>{cleanup();vi.clearAllMocks();for(const key of Object.keys(commands))delete commands[key];});

describe('coordinator candidates funnel',()=>{
  it('shows the section tabs, the waiting hero and four stages without opening a panel on load',()=>{
    page();
    expect(screen.getByRole('heading',{level:1,name:'Кандидаты'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'Собеседования'}).getAttribute('href')).toBe('/fund/interviews');
    expect(screen.getByRole('heading',{name:'2 новые анкеты ждут ответа'})).toBeTruthy();
    expect(['Новые анкеты','Знакомятся с фондом','Собеседование','Готовы к первому выходу'].map(title=>within(stageOf(title)).getByRole('heading').textContent)).toHaveLength(4);
    expect(within(stageOf('Новые анкеты')).getByText('2').className).toContain('is-hot');
    expect(screen.queryByRole('complementary')).toBeNull();
    expect(screen.queryByRole('button',{name:/Отказы и пауза/})).toBeNull();
    expect(document.body.textContent).not.toContain('·');
  });

  it('puts one value on each row: wait time, lessons, interview date and since when',()=>{
    page();
    expect(within(stageOf('Новые анкеты')).getByText('ждёт 3 дня').className).toBe('cand-late');
    expect(within(stageOf('Новые анкеты')).getByText('сегодня')).toBeTruthy();
    expect(within(stageOf('Знакомятся с фондом')).getByText('1 из 4 уроков')).toBeTruthy();
    expect(within(stageOf('Собеседование')).getByText('без даты')).toBeTruthy();
    expect(within(stageOf('Собеседование')).getByText('пт 23 окт, 10:00')).toBeTruthy();
    expect(within(stageOf('Готовы к первому выходу')).getByText('с 21 окт')).toBeTruthy();
  });

  it('opens the first new candidate from the hero and accepts or declines with the review command',async()=>{
    page();
    fireEvent.click(screen.getByRole('button',{name:'Разобрать'}));
    const panel=screen.getByRole('complementary',{name:'Полина Тестова'});
    expect(within(panel).getByText('Продавала на маркетах')).toBeTruthy();
    expect(within(panel).getByRole('link',{name:'Telegram @polina'}).getAttribute('href')).toBe('https://t.me/polina');
    expect(within(panel).getByRole('link',{name:'Вся анкета'}).getAttribute('href')).toBe('/fund/candidates/polina');
    expect(screen.getByTestId('where').textContent).toBe('/fund/candidates?candidate=polina');
    fireEvent.click(within(panel).getByRole('button',{name:'Принять анкету'}));
    expect(commands['/api/v1/coord/candidates/polina/review'].mutateAsync).toHaveBeenCalledWith({body:{expected_version:2,state:'reviewing',public_message:'Анкета принята. Следующий шаг: знакомство с фондом.',assigned_coordinator_id:'me'}});
    fireEvent.click(within(panel).getByRole('button',{name:'Отказать'}));
    fireEvent.click(within(panel).getByRole('button',{name:'Отказать'}));
    expect(commands['/api/v1/coord/candidates/polina/review'].mutateAsync).toHaveBeenLastCalledWith({body:{expected_version:2,state:'closed',public_message:'',assigned_coordinator_id:null}});
    await vi.waitFor(()=>expect(screen.queryByRole('complementary')).toBeNull());
  });

  it('offers the next step for each stage',()=>{
    page();
    fireEvent.click(screen.getByRole('button',{name:/Анна Тестова/}));
    const intro=screen.getByRole('complementary');
    expect(within(intro).getByText('Знакомство с фондом').closest('li')?.getAttribute('aria-current')).toBe('step');
    fireEvent.click(within(intro).getByRole('button',{name:'Напомнить про знакомство'}));
    expect(commands['/api/v1/coord/candidates/anna/remind'].mutateAsync).toHaveBeenCalledWith({body:{expected_version:2}});
    fireEvent.click(screen.getByRole('button',{name:/Мария Тестова/}));
    expect(within(screen.getByRole('complementary')).getByRole('link',{name:'Предложить время'}).getAttribute('href')).toBe('/fund/interviews/availability');
    fireEvent.click(screen.getByRole('button',{name:/Тимур Тестова/}));
    expect(within(screen.getByRole('complementary')).getByRole('link',{name:'Открыть собеседование'}).getAttribute('href')).toBe('/fund/interviews?booking=booking-1');
    fireEvent.click(screen.getByRole('button',{name:/Сергей Тестова/}));
    expect(within(screen.getByRole('complementary')).getByRole('link',{name:'Подобрать первое мероприятие'}).getAttribute('href')).toBe('/fund/opportunities');
    fireEvent.click(screen.getByRole('button',{name:'Закрыть'}));
    expect(screen.queryByRole('complementary')).toBeNull();
  });

  it('keeps a recent reminder visible and hides the hero when nothing waits',()=>{
    lists.new=[];summary={...summary,new:0};
    lists.intro=[{...learning,history:[{id:'e',kind:'reminded',state:'reviewing',public_message:'',created_at:ago(0)}]}];
    page('/fund/candidates?candidate=anna');
    expect(screen.queryByRole('button',{name:'Разобрать'})).toBeNull();
    expect(within(stageOf('Новые анкеты')).getByText('Никого')).toBeTruthy();
    expect((screen.getByRole('button',{name:'Напоминание отправлено'}) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows four rows of a long stage until «Показать все» and keeps paused people reachable',()=>{
    lists.ready=many;lists.closed=[person('lost','Ольга','closed',{review_state:'paused'})];summary={...summary,ready:6,closed:1};
    page();
    const block=stageOf('Готовы к первому выходу');
    expect(within(block).getAllByRole('button',{name:/Готов\d/})).toHaveLength(4);
    fireEvent.click(within(block).getByRole('button',{name:'Показать все'}));
    expect(within(block).getAllByRole('button',{name:/Готов\d/})).toHaveLength(6);
    fireEvent.click(screen.getByRole('button',{name:/Отказы и пауза/}));
    fireEvent.click(within(stageOf('Отказы и пауза')).getByRole('button',{name:/Ольга Тестова/}));
    expect(within(screen.getByRole('complementary')).getByText('Анкета на паузе')).toBeTruthy();
    expect(within(screen.getByRole('complementary')).getByRole('button',{name:'Вернуться к рассмотрению'})).toBeTruthy();
  });
});
