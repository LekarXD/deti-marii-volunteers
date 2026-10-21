import {useState} from 'react';
import type {Meta,StoryObj} from '@storybook/react';
import {Button,Card,Field,Input,Textarea,Combobox,Segmented} from './controls';
import {DatePicker,TimePicker} from './pickers';
import {Dialog,Drawer,EmptyState,LoadingState,ErrorState,JobState,Skeleton} from './overlays';
import {ApiError} from '../api/transport';
import {FoundationPreview} from './FoundationPreview';
import {CandidateLayout,CoordinatorLayout} from '../app/layouts/Layouts';
import {UploadControl} from './UploadControl';
import type {components} from '../api/generated/schema';
const uploadFixture:components['schemas']['AssetView']={id:'00000000-0000-4000-8000-000000000001',content_type:'image/png',expected_size:1000,received_size:620,state:'processing',upload_url:'/api/v1/assets/fixture/upload'};
const meta:Meta={title:'Опора/Основы',tags:['autodocs']};
export default meta;
type Story=StoryObj;
export const FullFoundation:Story={name:'Общая библиотека',render:()=> <FoundationPreview/>};
export const Buttons:Story={name:'Кнопки и состояния',render:()=> <Card><h2 className="h2">Один язык действий</h2><div className="actions">{(['primary','accent','secondary','ghost','subtle','danger'] as const).map(variant=><Button key={variant} variant={variant}>{({primary:'Продолжить',accent:'Записаться',secondary:'Назад',ghost:'Отмена',subtle:'Подробнее',danger:'Удалить'})[variant]}</Button>)}</div><div className="actions"><Button size="sm">Небольшая</Button><Button size="lg">Большая</Button><Button loading>Сохраняем</Button><Button disabled>Недоступно</Button></div></Card>};
function FormFixture(){const [value,setValue]=useState('arts');const [date,setDate]=useState('2026-12-31');const [time,setTime]=useState('18:15');return <Card><div className="stack"><Field label="Как вас зовут" error="Укажите имя, чтобы координатор мог к вам обратиться"><Input autoComplete="given-name"/></Field><Field label="Что вы любите делать" hint="Можно коротко, своими словами"><Textarea placeholder="Расскажите немного о себе"/></Field><Combobox label="Направление" value={value} onChange={setValue} options={[{value:'arts',label:'Творческие мастерские'},{value:'events',label:'Помощь в организации занятий и мероприятий с участниками и волонтёрами фонда'},{value:'closed',label:'Направление закрыто',disabled:true}]}/><DatePicker label="День встречи" value={date} onChange={setDate}/><TimePicker label="Начало" value={time} onChange={setTime} min="09:00" max="20:00"/></div></Card>;}
export const Forms:Story={name:'Формы, ошибки и длинные подписи',render:()=> <FormFixture/>};
function OverlayFixture(){const [parent,setParent]=useState(false);const [child,setChild]=useState(false);return <><Button onClick={()=>setParent(true)}>Открыть карточку</Button><Drawer open={parent} onClose={()=>setParent(false)} title="Собеседование с волонтёром" footer={<Button onClick={()=>setChild(true)}>Подтвердить встречу</Button>}><p className="lead">Нажмите Tab, Shift+Tab и Escape, чтобы проверить порядок фокуса.</p><Input aria-label="Комментарий"/><Dialog open={child} onClose={()=>setChild(false)} title="Проверим время встречи" footer={<Button onClick={()=>setChild(false)}>Вернуться к карточке</Button>}><p className="p">Закрытие диалога возвращает фокус в карточку. Закрытие карточки — к исходной кнопке.</p></Dialog></Drawer></>;}
export const Overlays:Story={name:'Вложенные окна и фокус',render:()=> <OverlayFixture/>};
export const States:Story={name:'Ответы API: загрузка, пусто, ошибка, обработка',render:()=> <div className="grid-2"><Card><LoadingState/><Skeleton/></Card><Card><EmptyState title="Встреч пока нет" description="Выберите удобное время для знакомства." action={<Button variant="secondary">Выбрать время</Button>}/></Card><Card><ErrorState error={new ApiError(503,'temporarily_unavailable','Сервис временно недоступен. Попробуйте ещё раз.')} retry={()=>{}}/></Card><Card><JobState status="queued"/><JobState status="processing"/><JobState status="ready"/><JobState status="failed"/><JobState status="unavailable"/></Card></div>};
export const Upload:Story={name:'Загрузка и обработка файла',render:()=> <Card><UploadControl label="Фото участника" accept="image/jpeg,image/png" onFile={()=>{}} progress={uploadFixture.received_size/uploadFixture.expected_size*100} status={uploadFixture.state==='processing'?'processing':'queued'}/></Card>};
export const CandidateHeader:Story={name:'Верхняя навигация волонтёра',parameters:{fullLayout:true,route:'/application'},render:()=> <CandidateLayout><FoundationPreview/></CandidateLayout>};
export const CoordinatorHeader:Story={name:'Верхняя навигация команды фонда',parameters:{fullLayout:true,route:'/fund/interviews'},render:()=> <CoordinatorLayout><FoundationPreview/></CoordinatorLayout>};
