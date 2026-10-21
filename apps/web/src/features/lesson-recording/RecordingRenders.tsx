import {useState} from 'react';
import {Link} from 'react-router-dom';
import {useSession} from '../../app/layouts/AppProviders';
import {Button,Card,Dialog,ErrorState,Field,Icon,LoadingState,Textarea} from '../../ui';
import {useRecordingCommand,useRecordingRenders,type RecordingProject,type RecordingRender} from './api';
const labels:Record<string,string>={queued:'Ожидает обработки',rendering:'Обрабатываем запись',provider_processing:'Подготавливаем файл',preview_ready:'Готово к просмотру',degraded:'Нужно проверить качество',failed:'Не удалось подготовить запись'};
export function RecordingRenders({project}:{project:RecordingProject}) {
 const query=useRecordingRenders(project.id);
 return <section className="section" aria-labelledby="recording-renders"><div className="section-head"><h2 className="h2" id="recording-renders">Просмотр и проверка</h2></div>
 {query.isPending?<LoadingState label="Проверяем результаты обработки…"/>:query.error?<ErrorState error={query.error} retry={()=>{void query.refetch();}}/>:query.data?.pages.some(page=>page.items.length)?<div className="recording-results">{query.data.pages.flatMap(page=>page.items).map(render=><RenderCard key={`${render.id}:${render.render_hash}:${render.version}`} project={project} render={render}/>)}</div>:<Card><h3 className="h3">Готовых файлов пока нет</h3><p className="p">После завершения дубля здесь появятся состояние обработки и приватный просмотр.</p></Card>}
 {query.hasNextPage&&<Button variant="secondary" loading={query.isFetchingNextPage} onClick={()=>{void query.fetchNextPage();}}>Ещё результаты</Button>}
 </section>;
}
function RenderCard({project,render}:{project:RecordingProject;render:RecordingRender}) {
 const {session}=useSession(),command=useRecordingCommand<RecordingRender>(),[preview,setPreview]=useState(false),[checked,setChecked]=useState(false),[reason,setReason]=useState(''),[mediaError,setMediaError]=useState(false);
 const playable=['preview_ready','degraded'].includes(render.state)&&!!render.asset_id&&!!render.content_hash;
 const canReview=session?.permissions.includes('recordings.review')===true;
 const canTransfer=render.approval_state==='approved'&&!!project.target_lesson_id&&session?.permissions.includes('learning.write')===true;
 async function decide(action:'approve'|'reject'){try{await command.mutateAsync({path:`/recording-renders/${render.id}/${action}`,body:{expected_version:render.version,render_hash:render.render_hash,reason:reason.trim()}});setPreview(false);setChecked(false);}catch{}}
 return <Card><div className="recording-result-heading"><span className="art art-y" aria-hidden="true"><Icon name="film"/></span><div className="grow"><h3 className="h3">{labels[render.state]??'Проверяем запись'}</h3>{render.approval_state==='approved'?<p className="recording-status"><Icon name="check"/>Запись согласована</p>:render.approval_state==='rejected'?<p className="p">Запись отклонена. Можно подготовить новый дубль.</p>:<p className="meta">Результат ещё не согласован</p>}</div></div>
 {render.duration_ms!==null&&<p className="meta">Длительность файла: {Math.floor(render.duration_ms/60000)}:{String(Math.floor(render.duration_ms/1000)%60).padStart(2,'0')}</p>}
 {render.state==='degraded'&&<p className="recording-note">Качество записи требует внимания. Проверь весь файл перед согласованием.</p>}
 {render.state==='failed'&&<p className="p">Не удалось получить готовый файл. Можно записать новый дубль.</p>}
 <div className="recording-actions">{playable&&<Button variant="secondary" onClick={()=>{setMediaError(false);setPreview(true);}}>Посмотреть приватно</Button>}{canTransfer&&<Link className="btn btn-primary" to={`/fund/learning/lessons/${encodeURIComponent(project.target_lesson_id!)}?recording_render_id=${encodeURIComponent(render.id)}`}>Передать в урок</Link>}{render.approval_state==='approved'&&!project.target_lesson_id&&<p className="p">Выбери урок в настройках проекта, чтобы передать запись в черновик.</p>}</div>
 <Dialog open={preview} onClose={()=>setPreview(false)} title="Проверка записи"><div className="recording-form">{playable&&<video key={`${render.asset_id}:${render.content_hash}`} controls playsInline preload="metadata" src={`/api/v1/assets/${encodeURIComponent(render.asset_id!)}/content`} onError={()=>setMediaError(true)} aria-label="Приватная запись урока"/>}{mediaError&&<p role="alert">Не удалось загрузить файл записи. Закрой просмотр и попробуй снова.</p>}<p className="p">Проверь изображение и звук во всём уроке. Согласование записи ещё не публикует её волонтёрам.</p>{canReview&&<><label className="recording-check"><input type="checkbox" checked={checked} onChange={event=>setChecked(event.target.checked)}/><span>Я проверил изображение и звук</span></label><Field label="Комментарий к проверке (необязательно)"><Textarea value={reason} onChange={event=>setReason(event.target.value)} maxLength={4000}/></Field><div className="recording-actions"><Button disabled={!checked||mediaError||command.isPending} loading={command.isPending} onClick={()=>{void decide('approve');}}>Согласовать запись</Button><Button variant="ghost" disabled={command.isPending} onClick={()=>{void decide('reject');}}>Отклонить запись</Button></div></>}{command.error&&<ErrorState error={command.error}/>}</div></Dialog>
 </Card>;
}
