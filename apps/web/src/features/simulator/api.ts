import {useRef} from 'react';
import {useInfiniteQuery,useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type ScenarioDraft=components['schemas']['SimulatorScenarioDraft'];
export type ScenarioStaff=components['schemas']['SimulatorScenarioStaffView'];
export type ScenarioPublic=components['schemas']['SimulatorScenarioPublicView'];
export type SimulationAttempt=components['schemas']['SimulatorSessionView'];
export type SimulationAssessment=components['schemas']['SimulatorAssessmentOutput'];
export type SimulationTestRun=components['schemas']['SimulatorTestRunView'];
export type ReviewQueueItem=components['schemas']['SimulatorReviewQueueItem'];
export type AppealDetail=components['schemas']['SimulatorAppealDetail'];
export type TestCaseResult={key:string;state:string;expected_scores:Record<string,0|1|2>;result?:{actual_scores?:Record<string,number>;error_code?:string}|null};
export function useScenarios(staff=false){return useInfiniteQuery({queryKey:keys.list('simulator',{staff}),initialPageParam:'',queryFn:({signal,pageParam})=>api<{items:(ScenarioStaff|ScenarioPublic)[];next_cursor?:string|null}>(`${staff?'/coord':''}/simulator/scenarios?limit=100${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor??undefined})}
export function usePublishedScenario(id:string|undefined){return useQuery({queryKey:keys.detail('simulator',`published:${id}`),enabled:!!id,queryFn:({signal})=>api<ScenarioPublic>(`/simulator/scenarios/${id}`,{signal})})}
export function useStaffScenario(id:string|undefined){return useQuery({queryKey:keys.detail('simulator',`staff:${id}`),enabled:!!id,queryFn:({signal})=>api<ScenarioStaff>(`/coord/simulator/scenarios/${id}`,{signal}),refetchInterval:query=>query.state.data?.test_runs.some(run=>['running','queued'].includes(String(run.state)))?1500:false})}
export function useScenarioExamples(enabled=true){return useQuery({enabled,queryKey:keys.list('simulator',{kind:'examples'}),queryFn:({signal})=>api<ScenarioDraft[]>('/coord/simulator/examples',{signal})})}
export function useSimulation(id:string|undefined){return useQuery({queryKey:keys.detail('simulator',`attempt:${id}`),enabled:!!id,queryFn:({signal})=>api<SimulationAttempt>(`/simulation-sessions/${id}`,{signal}),refetchInterval:query=>['waiting_reply','evaluating'].includes(query.state.data?.state??'')?1500:false})}
export function useSimulationHistory(){return useInfiniteQuery({queryKey:keys.list('simulator',{kind:'own-attempts'}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['SimulatorSessionPage']>(`/simulation-sessions?limit=30${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor??undefined})}
export function useSimulatorTest(id:string|undefined){return useQuery({queryKey:keys.detail('simulator',`test:${id}`),enabled:!!id,queryFn:({signal})=>api<SimulationTestRun>(`/coord/simulator/test-runs/${id}`,{signal}),refetchInterval:query=>['queued','running'].includes(query.state.data?.state??'')?1500:false})}
export function useSimulatorQueue(kind:'appeals'|'support-requests',enabled=true){return useQuery({enabled,queryKey:keys.list('simulator',{kind}),queryFn:({signal})=>api<ReviewQueueItem[]>(`/coord/simulator/${kind}`,{signal})})}
export function useSimulatorAppeal(id:string|undefined){return useQuery({queryKey:keys.detail('simulator',`appeal:${id}`),enabled:!!id,queryFn:({signal})=>api<AppealDetail>(`/coord/simulator/appeals/${id}`,{signal})})}
export function useSimulatorCommand(){const client=useQueryClient();const attempts=useRef(new Map<string,string>());return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:'POST'|'PATCH'})=>{const fingerprint=JSON.stringify([path,method,body]);const key=attempts.current.get(fingerprint)??crypto.randomUUID();attempts.current.set(fingerprint,key);return api<SimulationAttempt|ScenarioStaff|SimulationTestRun|components['schemas']['SimulatorSimpleResult']>(path,{method,body,idempotencyKey:key})},onSuccess:(_result,variables)=>{attempts.current.delete(JSON.stringify([variables.path,variables.method??'POST',variables.body]));return client.invalidateQueries({queryKey:keys.all('simulator')})}})}
