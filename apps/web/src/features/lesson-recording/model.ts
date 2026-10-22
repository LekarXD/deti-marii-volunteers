import type {RecordingTake} from './api';
import type {Track} from '../learning/authorApi';
/** Current lessons of current courses as picker choices, «Курс, урок». */
export const lessonChoices=(tracks:readonly Track[]|undefined)=>tracks?.filter(track=>!track.archived).flatMap(track=>track.lessons.filter(item=>!item.archived).map(item=>({value:item.id,label:`${track.title}, ${item.title}`})))??[];
export const lessonTitle=(tracks:readonly Track[]|undefined,id:string)=>tracks?.flatMap(track=>track.lessons).find(item=>item.id===id)?.title;
export const projectLabels:Record<string,string>={draft:'Черновик',prepared:'Студия подготовлена',has_takes:'Есть дубли',archived:'Проект закрыт'};
export const takeLabels:Record<string,string>={created:'Дубль подготовлен',starting:'Готовим запись',capturing:'Идёт запись',stopping:'Завершаем запись',captured:'Дубль записан',failed:'Запись не завершилась',discarded:'Дубль удалён'};
export const activeTake=(items:readonly RecordingTake[])=>items.find(take=>['created','starting','capturing','stopping'].includes(take.state));
export function recordingLimit(seconds:number) {
 if(!Number.isSafeInteger(seconds)||seconds<=0)return null;
 const minutes=Math.floor(seconds/60),remainder=seconds%60;
 return [minutes?`${minutes} мин`:null,remainder?`${remainder} с`:null].filter(Boolean).join(' ');
}
/** No locally simulated elapsed clock: only the confirmed stored interval is shown. */
export function takeDuration(take:RecordingTake) {
 if(!take.started_at||!take.stopped_at)return null;
 const elapsed=Date.parse(take.stopped_at)-Date.parse(take.started_at);
 if(!Number.isFinite(elapsed)||elapsed<0)return null;
 const seconds=Math.round(elapsed/1000);return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
}
export function deviceError(error:unknown,device:'camera'|'microphone'|'screen'|'connection') {
 const label={camera:'камере',microphone:'микрофону',screen:'экрану',connection:'студии'}[device];
 // DOMException may come from the browser/SDK's different realm.
 const name=error&&typeof error==='object'&&'name' in error&&typeof error.name==='string'?error.name:'';
 if(name==='NotAllowedError'||name==='PermissionDeniedError')return `Доступ к ${label} не разрешён. Проверьте разрешения браузера и попробуйте снова.`;
 if(name==='NotFoundError'||name==='DevicesNotFoundError')return 'Устройство не найдено. Подключите его или выберите другое.';
 if(name==='NotReadableError'||name==='TrackStartError')return 'Устройство занято или недоступно. Закройте другое приложение и попробуйте снова.';
 return device==='connection'?'Не удалось подключиться к студии. Проверьте соединение и попробуйте снова.':`Не удалось включить доступ к ${label}. Можно повторить попытку.`;
}
