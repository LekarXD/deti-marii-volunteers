import {useEffect, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {keys} from '../../api/keys';
import {Button, Card, ErrorState, Icon, LoadingState} from '../../ui';
import {usePersonalSchedule, type AssignmentParticipation} from '../activities/participationApi';
import {usePreparation} from '../learning/api';
import {readPreparation} from '../followups/api';
import {assignmentWhen, homeScheduleRange, learningDestination, upcomingAssignments} from './model';
import './home.css';

/** CandidateLayout is supplied by the router; this page owns only the home content. */
export function HomePage() {
  const [now, setNow] = useState(Date.now);
  const {from,to}=homeScheduleRange(now);
  const assignments = usePersonalSchedule(from,to,'active');
  const learning = usePreparation();
  useEffect(() => {const timer = window.setInterval(() => {setNow(Date.now()); void assignments.refetch();}, 30_000); return () => window.clearInterval(timer);}, [assignments.refetch]);
  // Cursor order is by UUID: a partial date window cannot establish the nearest
  // event. Remaining pages require an explicit action rather than an unbounded scan.
  const items = assignments.data?.pages.flatMap(page => page.items) ?? [];
  const upcoming = upcomingAssignments(items, now);
  const complete = !assignments.isPending && !assignments.hasNextPage && !assignments.isError;
  const next = complete ? upcoming[0] : undefined;
  const confirmed = complete ? upcoming.find(item => item.status === 'confirmed') : undefined;
  const preparation = useQuery({
    queryKey: keys.detail('assignment-preparation', confirmed?.id ?? ''),
    queryFn: ({signal}) => readPreparation(confirmed!.id, signal),
    enabled: Boolean(confirmed), staleTime: 0, refetchInterval: 15_000,
  });
  const invitations = upcoming.filter(item => item.status === 'invited');
  const retryAssignments = () => {void (assignments.isFetchNextPageError ? assignments.fetchNextPage() : assignments.refetch());};
  const tracks = learning.data?.assignments ?? [];
  const track = tracks.find(item => !item.completed) ?? tracks[0];
  const completedLessons = track?.lessons.filter(lesson => lesson.completed).length ?? 0;

  return <div className="volunteer-home">
    <h1 className="h1 home-greeting">Привет!</h1>
    {assignments.isError ? <Card><ErrorState error={assignments.error} retry={retryAssignments}/></Card>
      : assignments.isPending ? <Card tone="hero"><LoadingState label="Ищем ближайшее занятие…"/></Card>
      : !complete ? <Card tone="hero"><h2 className="h2">Расписание загружено не полностью</h2><p className="lead">В ближайшие 90 дней есть ещё занятия. Загрузи следующую страницу, чтобы определить ближайшее.</p><Button loading={assignments.isFetchingNextPage} onClick={() => {void assignments.fetchNextPage();}}>Загрузить ещё занятия</Button></Card>
      : next ? <NextAssignment item={next} now={now}/>
      : <Card tone="hero"><div className="hero-grid"><div className="home-hero-copy">
        <p className="eyebrow">Моё участие</p>
        <h2 className="hero-when">Впереди новые встречи</h2>
        <p className="lead">На ближайшие 90 дней занятий пока нет. Посмотри, где сейчас нужна помощь.</p>
        <div className="home-actions"><Link className="btn btn-primary btn-lg" to="/opportunities">Где нужна помощь</Link><Link className="btn btn-secondary btn-lg" to="/my/assignments">Моё участие</Link></div>
        <p className="p home-newcomer">Только знакомишься с фондом? <Link to="/application">Моя анкета</Link> · <Link to="/interviews">Знакомство с координатором</Link></p>
      </div><span className="hero-art" aria-hidden="true"><Icon name="academy"/></span></div></Card>}

    {complete && invitations.length > 0 && <section className="section" aria-labelledby="home-invitations">
      <div className="section-head"><h2 className="h2" id="home-invitations">Тебя приглашают</h2><Link className="btn btn-ghost btn-sm" to="/my/assignments">Все приглашения</Link></div>
      <div className="grid-3">{invitations.slice(0, 3).map(item => <Link className="card match home-invitation" key={item.id} to={`/my/assignments/${item.id}`}>
        <span className="art art-y" aria-hidden="true"><Icon name="calendar"/></span><span><span className="h3">{item.title}</span><span className="p home-line">{assignmentWhen(item, now).date} · {assignmentWhen(item, now).time}</span><span className="meta home-line">{item.timezone}</span></span><span className="match-foot"><span>Ответить на приглашение</span><Icon name="arrow-right"/></span>
      </Link>)}</div>
    </section>}

    <div className="grid-2 section home-support-grid">
      <section className="card home-learning" aria-labelledby="home-learning">
        <p className="eyebrow">Обучение</p>
        <h2 className="h3 home-card-title" id="home-learning">{track?.title ?? 'Учимся помогать вместе'}</h2>
        {learning.isPending ? <LoadingState label="Загружаем обучение…"/> : learning.error ? <ErrorState error={learning.error} retry={() => {void learning.refetch();}}/> : track ? <>
          {track.intro && <p className="p">{track.intro}</p>}
          {track.lessons.length > 0 && <div className="row home-learning-progress"><progress value={completedLessons} max={track.lessons.length} aria-label="Пройдено уроков"/><span className="strong num">{completedLessons} из {track.lessons.length}</span></div>}
          <p className="meta">{track.completed ? 'Трек пройден' : track.reacknowledgement_required ? 'Нужно познакомиться с обновлениями' : 'Можно продолжить в своём темпе'}</p>
          <Link className="btn btn-secondary" to={learningDestination(track)}>{track.completed ? 'Открыть материалы' : 'Продолжить обучение'}</Link>
        </> : <><p className="p">Координатор подберёт материалы для твоей роли. Назначенные треки появятся здесь.</p><Link className="btn btn-secondary" to="/academy">Перейти в обучение</Link></>}
      </section>
      <section className="card home-preparation" aria-labelledby="home-preparation">
        <p className="eyebrow">Перед выходом</p><h2 className="h3 home-card-title" id="home-preparation">{confirmed ? 'Кто встретит и что взять' : 'Подготовка к следующему выходу'}</h2>
        {confirmed ? <>
          <p className="p">{confirmed.title}</p>
          {preparation.isPending ? <LoadingState label="Загружаем памятку…"/> : preparation.error ? <ErrorState error={preparation.error} retry={() => {void preparation.refetch();}}/> : preparation.data && <>
            {preparation.data.contacts.length > 0 ? <ul className="home-contacts">{preparation.data.contacts.map((contact, index) => <li key={`${contact.role}-${index}`}><Icon name="user"/><span><b>{contact.display_name}</b><span className="meta home-line">{contact.role}</span></span></li>)}</ul> : <p className="meta">Координатор уточнит, кто встретит тебя.</p>}
            {preparation.data.location && <p className="p home-location"><Icon name="pin"/>{preparation.data.location}</p>}
            {preparation.data.checklist.length > 0 && <p className="p">Перед выходом: {preparation.data.checklist.filter(item => item.checked).length} из {preparation.data.checklist.length} пунктов выполнено</p>}
            {preparation.data.checklist.some(item => !item.checked) && <ul className="home-checklist">{preparation.data.checklist.filter(item => !item.checked).slice(0, 3).map(item => <li key={item.key}>{item.title}</li>)}</ul>}
          </>}
          <Link className="btn btn-secondary" to={`/my/assignments/${confirmed.id}/preparation`}>Открыть памятку</Link>
        </> : <><p className="p">После подтверждения участия здесь будут памятка, контакты и список подготовки к занятию.</p><Link className="btn btn-secondary" to={invitations.length ? '/my/assignments' : '/opportunities'}>{invitations.length ? 'Посмотреть приглашения' : 'Посмотреть возможности'}</Link></>}
      </section>
    </div>
    <section className="section card-soft home-help" aria-labelledby="home-help"><span className="art art-v" aria-hidden="true"><Icon name="message"/></span><div className="grow"><h2 className="h3" id="home-help">Есть вопрос перед занятием?</h2><p className="p">Договорённости и вопросы можно обсудить с координатором.</p></div><Link className="btn btn-secondary" to={confirmed ? `/my/assignments/${confirmed.id}/preparation#before-question` : '/messages'}>{confirmed ? 'Задать вопрос' : 'Открыть сообщения'}</Link></section>
  </div>;
}
function NextAssignment({item, now}: {item: AssignmentParticipation; now: number}) {
  const when = assignmentWhen(item, now);
  const confirmed = item.status === 'confirmed';
  return <Card tone="hero" aria-labelledby="home-next"><div className="hero-grid"><div className="home-hero-copy">
    <p className="eyebrow">{confirmed ? 'Ближайшее занятие' : 'Ближайшее приглашение'}</p>
    <h2 className="hero-when" id="home-next">{when.date}{' '}<span className="home-line">{when.time}</span></h2>
    <p className="lead">{item.title}</p><p className="p">{[item.location, item.timezone].filter(Boolean).join(' · ')}</p>
    <div className="home-actions"><Link className="btn btn-primary btn-lg" to={`/my/assignments/${item.id}${confirmed ? '/preparation' : ''}`}>{confirmed ? 'Подготовиться к выходу' : 'Ответить на приглашение'}</Link><Link className="btn btn-secondary btn-lg" to="/my/assignments">Моё участие</Link></div>
    {confirmed && <div className="hero-note"><span className="row strong"><Icon name="check"/>Участие подтверждено</span></div>}
  </div><span className="hero-art" aria-hidden="true"><Icon name="palette"/></span></div></Card>;
}
