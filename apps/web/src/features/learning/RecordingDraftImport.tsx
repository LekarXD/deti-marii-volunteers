import {useEffect,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {Button,Card,ErrorState,LoadingState} from '../../ui';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {useAuthorCommand,type AuthorLesson} from './authorApi';

type RecordingRender=components['schemas']['RecordingRenderView'];
export function RecordingDraftImport({lessonId,draftVersion,disabled,onApplied}:{lessonId:string;draftVersion:number;disabled:boolean;onApplied:(lesson:AuthorLesson)=>void}){
 const [search]=useSearchParams(),renderId=search.get('recording_render_id');
 const client=useQueryClient(),command=useAuthorCommand(),[added,setAdded]=useState(false);
 useEffect(()=>setAdded(false),[renderId]);
 const render=useQuery({queryKey:keys.detail('learning-recording-import',renderId??''),queryFn:({signal})=>api<RecordingRender>(`/recording-renders/${renderId}/status`,{signal}),enabled:!!renderId,retry:false});
 if(!renderId)return null;
 const ready=render.data?.approval_state==='approved'&&!!render.data.asset_id&&['preview_ready','degraded'].includes(render.data.state);
 async function attach(){
  if(!render.data||!ready)return;
  try{
   const lesson=await command.mutateAsync({path:`/lessons/${lessonId}/recording`,body:{expected_version:draftVersion,render_id:render.data.id,render_hash:render.data.render_hash}}) as AuthorLesson;
   onApplied(lesson);setAdded(true);
  }catch{await Promise.all([render.refetch(),client.invalidateQueries({queryKey:keys.all('learning-author')})]);}
 }
 return <Card tone="soft"><p className="eyebrow">Запись для этого урока</p><h2>{added?'Видео добавлено в черновик':'Перенести согласованную запись'}</h2>{render.isPending?<LoadingState label="Проверяем запись…"/>:render.error?<ErrorState error={render.error} retry={()=>void render.refetch()}/>:<><p>{added?'Посмотрите урок глазами волонтёра, затем согласуйте редакцию. Публикация трека выполняется отдельно.':ready?'Запись прошла согласование. Она добавится последним блоком; остальные материалы урока сохранятся.':'Эта версия записи ещё не согласована или уже изменилась. Откройте проект записи и проверьте актуальную версию.'}</p>{disabled&&!added&&<p role="status">Сначала сохраните изменения урока, чтобы добавить запись.</p>}<div className="actions"><Button disabled={!ready||disabled||added||command.isPending} onClick={()=>void attach()}>{command.isPending?'Добавляем…':'Добавить в черновик'}</Button>{render.data&&<Link to={`/fund/recordings/${render.data.project_id}`}>Открыть проект записи</Link>}</div></>}{command.error&&<ErrorState error={command.error}/>}</Card>;
}
