import {useEffect, useRef, useState, type ReactNode} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {keys} from '../../api/keys';
import {Button, ErrorState, Icon, LoadingState, type IconName} from '../../ui';
import {awaitingCoordinator, multiplierLabel, usePersonalSchedule, type AssignmentParticipation} from '../activities/participationApi';
import {feedRange, toneFor, useEventFeed, type EventCard, type EventFeed} from '../activities/eventsApi';
import {EventTile} from '../activities/EventTile';
import {usePreparation} from '../learning/api';
import {readPreparation, type Preparation} from '../followups/api';
import {readAssignmentBriefing} from '../participants/api';
import {pointsLabel, useHours, useProfile} from '../profile/api';
import {canDecline, confirmCommand, declineCommand, lateCommand, useHomeCommand} from './api';
import {
  answerable, assignmentWhen, coordinatorContact, firstName, hadConfirmedPast, heroEyebrow, heroKind, homePastRange, homeScheduleRange, initials, lateSent,
  learningDestination, learningProgress, meetingContact, pathLine, pickedEvents, startPath, upcomingAssignments, type HeroKind,
} from './model';
import './home.css';

type Answer = {state: 'yes' | 'no'; item: AssignmentParticipation};
const byStart = (a: AssignmentParticipation, b: AssignmentParticipation) => Date.parse(a.starts_at) - Date.parse(b.starts_at) || a.id.localeCompare(b.id);

/** The volunteer layout is supplied by the router; this page owns only the home content (Home.dc.html). */
export function HomePage() {
  const [now, setNow] = useState(Date.now);
  const {from, to} = homeScheduleRange(now);
  const assignments = usePersonalSchedule(from, to, 'active');
  const pastRange = homePastRange(now);
  const past = usePersonalSchedule(pastRange.from, pastRange.to);
  const learning = usePreparation();
  const hours = useHours();
  const profile = useProfile();
  const feedPeriod = feedRange();
  const feed = useEventFeed(feedPeriod.from, feedPeriod.to);
  const [declined, setDeclined] = useState<AssignmentParticipation>();
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  useEffect(() => {const timer = window.setInterval(() => {setNow(Date.now()); void assignments.refetch();}, 30_000); return () => window.clearInterval(timer);}, [assignments.refetch]);
  // Cursor order is by UUID: a partial date window cannot establish the nearest
  // event. Remaining pages require an explicit action rather than an unbounded scan.
  const items = assignments.data?.pages.flatMap(page => page.items) ?? [];
  const complete = !assignments.isPending && !assignments.hasNextPage && !assignments.isError;
  const upcoming = complete ? upcomingAssignments(items, now) : [];
  const open = answerable(upcoming);
  const hero = declined ? undefined : open.find(item => !answers[item.id]);
  const pending = hero ? undefined : upcoming.find(awaitingCoordinator);
  const kind = hero && heroKind(hero, now);
  // A newcomer has no confirmed занятие that already ended. The past is read page by page until one is found.
  const pastItems = past.data?.pages.flatMap(page => page.items) ?? [];
  const hadPast = hadConfirmedPast(pastItems, now);
  useEffect(() => {if (!hadPast && past.hasNextPage && !past.isFetchingNextPage && !past.isError) void past.fetchNextPage();}, [hadPast, past.hasNextPage, past.isFetchingNextPage, past.isError]);
  const newbie = Boolean(hero) && past.isSuccess && !hadPast && !past.hasNextPage;
  const memoId = hero?.status === 'confirmed' ? hero.id : '';
  const preparation = useQuery({
    queryKey: keys.detail('assignment-preparation', memoId),
    queryFn: ({signal}) => readPreparation(memoId, signal),
    enabled: Boolean(memoId), staleTime: 0, refetchInterval: 15_000,
  });
  const memo = memoId ? preparation.data : undefined;
  const groupId = kind === 'today' && memo?.group_briefing_available ? memoId : '';
  const group = useQuery({
    queryKey: keys.detail('assignment-group-briefing', groupId),
    queryFn: ({signal}) => readAssignmentBriefing(groupId, signal),
    enabled: Boolean(groupId), retry: false, staleTime: 0, refetchInterval: 15_000,
  });
  const rows = new Map<string, AssignmentParticipation>();
  for (const item of open) if (item.status === 'invited' && item.id !== hero?.id && item.id !== declined?.id) rows.set(item.id, item);
  for (const [id, answer] of Object.entries(answers)) if (id !== hero?.id) rows.set(id, open.find(item => item.id === id) ?? answer.item);
  const invitations = [...rows.values()].sort(byStart);
  const picked = pickedEvents(feed.data);
  const name = firstName(profile.data?.display_name ?? items[0]?.display_name);
  const retryAssignments = () => {void (assignments.isFetchNextPageError ? assignments.fetchNextPage() : assignments.refetch());};

  return <div className="volunteer-home">
    <div className="page-head"><h1 className="h1">{name ? `Привет, ${name}!` : 'Привет!'}</h1></div>
    {assignments.isError ? <section className="card"><ErrorState error={assignments.error} retry={retryAssignments}/></section>
      : assignments.isPending ? <section className="card-hero calm"><LoadingState label="Ищем ближайшее занятие…"/></section>
      : !complete ? <CalmHero eyebrow="Ближайшее занятие" title="Расписание загружено не полностью" sub="Загрузи остальные занятия, чтобы увидеть ближайшее" icon="calendar"
        actions={<Button size="lg" loading={assignments.isFetchingNextPage} onClick={() => {void assignments.fetchNextPage();}}>Загрузить ещё занятия</Button>}/>
      : declined ? <DeclinedHero item={declined} now={now}/>
      : hero && kind ? <AssignmentHero key={hero.id} item={hero} kind={kind} newbie={newbie} now={now} memo={memo} onDeclined={setDeclined}/>
      : pending ? <PendingHero key={pending.id} item={pending} now={now}/>
      : <EmptyHero feed={feed.data}/>}

    {hero && kind === 'today' && <TodayGroup item={hero} memo={memo} people={group.data?.items ?? []}/>}
    {hero && newbie && <StartPath item={hero} memo={memo}/>}

    {invitations.length > 0 && <section className="sec" aria-labelledby="home-invitations">
      <div className="sec-head"><h2 className="h2" id="home-invitations">Тебя приглашают</h2></div>
      <div className="card home-invites">{invitations.map(item => <InvitationRow key={item.id} item={item} now={now} answer={answers[item.id]?.state}
        onAnswer={state => setAnswers(current => ({...current, [item.id]: {state, item}}))}/>)}</div>
    </section>}

    {kind !== 'today' && !newbie && picked.length > 0 && <Picked cards={picked}/>}

    <div className="grid-2 sec">
      <Learning learning={learning}/>
      <MyPath hours={hours}/>
    </div>

    <section className="sec">
      <Link className="card-soft row wrap home-ask" to="/mentor">
        <span className="row"><span className="art art-v" aria-hidden="true"><Icon name="sparkle"/></span><span className="h3">Не знаешь, как поступить на занятии?</span></span>
        <span className="btn btn-ai">Что делать, если…</span>
      </Link>
    </section>
  </div>;
}

function CalmHero({eyebrow, title, sub, icon, actions}: {eyebrow: string; title: string; sub: string; icon: IconName; actions: ReactNode}) {
  return <section className="card-hero calm" aria-labelledby="home-hero"><div className="hero-grid"><div className="hero-copy">
    <p className="eyebrow">{eyebrow}</p>
    <h2 className="hero-title" id="home-hero">{title}</h2>
    {sub && <p className="hero-sub">{sub}</p>}
    <div className="actions">{actions}</div>
  </div><span className="hero-art" aria-hidden="true"><Icon name={icon}/></span></div></section>;
}

/** Nothing ahead: a calm card, the yellow hero stays reserved for a real занятие. */
function EmptyHero({feed}: {feed?: EventFeed}) {
  const locked = feed && !feed.can_sign_up;
  const primary = !locked ? <Link className="btn btn-primary btn-lg" to="/events">Все мероприятия</Link>
    : feed.locked_reason === 'volunteer_paused' ? <Link className="btn btn-primary btn-lg" to="/profile">Открыть профиль</Link>
    : <Link className="btn btn-primary btn-lg" to="/interviews">Встреча с координатором</Link>;
  return <CalmHero eyebrow="Ближайшее занятие" title="Пока ничего не запланировано" icon="calendar"
    sub={locked ? feed.locked_message ?? 'Записаться пока нельзя' : 'Посмотри, где сейчас нужна помощь'}
    actions={<>{primary}<Link className="btn btn-secondary btn-lg" to="/my/schedule">Мои занятия</Link></>}/>;
}

/** FirstExit.dc.html «Планы изменились»: the decline is final, so there is no «Всё-таки приду». */
function DeclinedHero({item, now}: {item: AssignmentParticipation; now: number}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {heading.current?.focus();}, []);
  return <section className="card-hero calm" aria-labelledby="home-hero"><div className="hero-grid"><div className="hero-copy">
    <p className="eyebrow">Планы изменились</p>
    <h2 className="hero-title" id="home-hero" ref={heading} tabIndex={-1}>Подберём другую дату</h2>
    <p className="hero-sub">Координатор знает, что {assignmentWhen(item, now).day} ты не сможешь.</p>
    <div className="actions"><Link className="btn btn-primary btn-lg" to="/messages">Написать координатору</Link><Link className="btn btn-secondary btn-lg" to="/events">Все мероприятия</Link></div>
  </div><span className="hero-art" aria-hidden="true"><Icon name="calendar"/></span></div></section>;
}

/** A self sign-up or a freed reserve place is with the coordinator: nothing to answer, the request can still be withdrawn. */
function PendingHero({item, now}: {item: AssignmentParticipation; now: number}) {
  const command = useHomeCommand();
  const when = assignmentWhen(item, now);
  const reserve = item.origin === 'reserve';
  const withdraw = () => {void command.mutateAsync(declineCommand(item)).catch(() => {});};
  return <section className="card-hero calm" aria-labelledby="home-hero"><div className="hero-grid"><div className="hero-copy">
    <p className="eyebrow">{reserve ? 'Освободилось место из резерва' : 'Ждёт ответа координатора'}</p>
    <h2 className="hero-when" id="home-hero">{when.date}<span className="home-when-time">, {when.time}</span></h2>
    <p className="hero-sub"><span className="home-sub-time">{when.time}, </span>{item.title}<span className="home-sub-place">{item.location ? `, ${item.location}` : ''}</span></p>
    {reserve && <p className="hero-sub">Координатор подтвердит участие.</p>}
    <div className="actions">
      <Link className="btn btn-primary btn-lg" to={`/my/assignments/${item.id}`}>Подробнее</Link>
      {canDecline(item) && <Button variant="ghost" size="lg" loading={command.isPending} onClick={withdraw}>{reserve ? 'Не смогу' : 'Отменить заявку'}</Button>}
    </div>
    {command.error && <p className="home-error" role="alert">{command.error.message}</p>}
  </div><span className="hero-art" aria-hidden="true"><Icon name="clock"/></span></div></section>;
}

function AssignmentHero({item, kind, newbie, now, memo, onDeclined}: {item: AssignmentParticipation; kind: HeroKind; newbie: boolean; now: number; memo?: Preparation; onDeclined: (item: AssignmentParticipation) => void}) {
  const when = assignmentWhen(item, now);
  const command = useHomeCommand();
  const [asking, setAsking] = useState(false);
  const [late, setLate] = useState(false);
  const note = useRef<HTMLDivElement>(null);
  useEffect(() => {if (asking) note.current?.focus();}, [asking]);
  const leader = firstName(meetingContact(memo)?.display_name);
  const coordinator = firstName(coordinatorContact(memo)?.display_name);
  const lateKnown = late || lateSent(memo);
  const preparationHref = `/my/assignments/${item.id}/preparation`;
  const place = item.location ? `, ${item.location}` : '';
  const busy = (suffix: string) => command.isPending && Boolean(command.variables?.path.endsWith(suffix));
  const confirm = () => {void command.mutateAsync(confirmCommand(item)).then(() => setAsking(false)).catch(() => {});};
  const decline = () => {void command.mutateAsync(declineCommand(item)).then(() => onDeclined(item)).catch(() => {});};
  const sendLate = () => {void command.mutateAsync(lateCommand(item)).then(() => setLate(true)).catch(() => {});};
  const canConfirm = item.allowed_actions.includes('confirm');
  const declineButton = canDecline(item) && <Button variant="secondary" size="lg" disabled={command.isPending} onClick={() => setAsking(true)}>Не смогу</Button>;
  const actions = kind === 'today'
    ? <><Link className="btn btn-primary btn-lg" to={preparationHref}>Открыть памятку</Link>{!lateKnown && <Button variant="secondary" size="lg" loading={busy('/questions')} onClick={sendLate}>Опаздываю</Button>}</>
    : kind === 'invitation'
      ? <>{canConfirm ? <Button size="lg" loading={busy('/confirm')} onClick={confirm}>Я приду</Button> : <Link className="btn btn-primary btn-lg" to={`/my/assignments/${item.id}`}>Подробнее</Link>}
        {newbie && canConfirm ? <Link className="btn btn-secondary btn-lg" to={`/my/assignments/${item.id}`}>Подробнее</Link> : declineButton}</>
      : <><Link className="btn btn-primary btn-lg" to={preparationHref}>Подготовиться</Link>{declineButton}</>;

  return <section className="card-hero" aria-labelledby="home-hero"><div className="hero-grid"><div className="hero-copy">
    <p className="eyebrow">{heroEyebrow(kind, newbie)}</p>
    <h2 className="hero-when" id="home-hero">{kind === 'today' ? when.range : <>{when.date}<span className="home-when-time">, {when.time}</span></>}</h2>
    {kind === 'today'
      ? <p className="hero-sub">{item.title}{place}.{leader && ` ${leader} встретит у входа.`}</p>
      : <p className="hero-sub"><span className="home-sub-time">{when.time}, </span>{item.title}<span className="home-sub-place">{place}</span>{newbie && leader && `. Тебя встретит ${leader}.`}</p>}
    {asking
      ? <div className="hero-note" ref={note} tabIndex={-1} role="group" aria-labelledby="home-hero-ask">
        <span className="strong" id="home-hero-ask">Предупредить координатора, что не сможешь?</span>
        <Button size="sm" loading={busy('/decline') || busy('/cancel')} disabled={command.isPending} onClick={decline}>Да, не смогу</Button>
        <Button variant="ghost" size="sm" loading={busy('/confirm')} disabled={command.isPending} onClick={item.status === 'invited' && canConfirm ? confirm : () => setAsking(false)}>Я приду</Button>
      </div>
      : <div className="actions">{actions}</div>}
    {kind === 'today' && lateKnown && <div className="hero-note home-late" role="status"><span className="st st-ok" aria-hidden="true"><Icon name="check"/></span><span className="strong">{coordinator || 'Координатор'} знает, что ты задержишься</span></div>}
    {command.error && <p className="home-error" role="alert">{command.error.message}</p>}
  </div><span className="hero-art" aria-hidden="true"><Icon name={kind === 'today' ? 'clock' : 'palette'}/></span></div></section>;
}

const TINTS = ['ph-o', 'ph-v', 'ph-b', 'ph-g'];
function groupNames(people: {display_name: string}[]) {
  const names = people.map(person => person.display_name.trim()).filter(Boolean);
  return names.length > 5 ? `${names.slice(0, 4).join(', ')} и ещё ${names.length - 4}` : names.join(', ');
}
/** Day of the занятие: the group from the confirmed briefing and the person who meets the volunteer. */
function TodayGroup({item, memo, people}: {item: AssignmentParticipation; memo?: Preparation; people: {id: string; display_name: string}[]}) {
  const contact = meetingContact(memo);
  const available = Boolean(memo?.group_briefing_available);
  if (!available && !contact) return null;
  const href = `/me/group?assignment_id=${encodeURIComponent(item.id)}`;
  return <section className="sec" aria-labelledby="home-group">
    <div className="sec-head"><h2 className="h2" id="home-group">Сегодня в группе</h2>{available && <Link className="quiet-link" to={href}>Как общаться с ребятами</Link>}</div>
    {(people.length > 0 || contact) && <div className="grid-2">
      {people.length > 0 && <Link className="card action-card home-group" to={href}>
        <span className="row" aria-hidden="true">{people.slice(0, 4).map((person, index) => <span className={`ph ${TINTS[index % TINTS.length]}`} key={person.id}>{initials(person.display_name).charAt(0)}</span>)}</span>
        <h3 className="h3">{groupNames(people)}</h3>
      </Link>}
      {contact && <div className="card action-card">
        <div className="who"><span className="ph ph-lg ph-o" aria-hidden="true">{initials(contact.display_name)}</span><div><b>{firstName(contact.display_name) || contact.display_name}, {contact.role.toLowerCase()}</b><span className="meta">Встретит у входа</span></div></div>
        <div className="actions"><Link className="btn btn-secondary" to="/messages">Написать</Link></div>
      </div>}
    </div>}
  </section>;
}

function StartPath({item, memo}: {item: AssignmentParticipation; memo?: Preparation}) {
  const steps = startPath(item.status, firstName(meetingContact(memo)?.display_name), firstName(coordinatorContact(memo)?.display_name));
  return <section className="sec" aria-labelledby="home-start">
    <div className="sec-head"><h2 className="h2" id="home-start">Как проходит начало</h2></div>
    <ol className="path home-start">{steps.map((step, index) => <li className={`path-step ${step.state}`.trim()} key={step.title} aria-current={step.state === 'now' ? 'step' : undefined}>
      <span className="n">{step.state === 'done' ? <><Icon name="check"/><span className="sr-only">Пройдено</span></> : index + 1}</span>
      <b>{step.title}</b><span>{step.text}</span>
    </li>)}</ol>
  </section>;
}

function InvitationRow({item, now, answer, onAnswer}: {item: AssignmentParticipation; now: number; answer?: Answer['state']; onAnswer: (state: Answer['state']) => void}) {
  const when = assignmentWhen(item, now);
  const command = useHomeCommand();
  const [asking, setAsking] = useState(false);
  const group = useRef<HTMLSpanElement>(null);
  useEffect(() => {if (asking) group.current?.focus();}, [asking]);
  const canConfirm = item.allowed_actions.includes('confirm');
  const busy = (suffix: string) => command.isPending && Boolean(command.variables?.path.endsWith(suffix));
  const send = (state: Answer['state']) => {void command.mutateAsync(state === 'yes' ? confirmCommand(item) : declineCommand(item)).then(() => {setAsking(false); onAnswer(state);}).catch(() => {});};
  return <div className="rowi home-invite">
    <div className="home-invite-main">
      <span className={`day ${toneFor(item.title).key}`} aria-hidden="true"><b>{when.dayNumber}</b><span>{when.weekday}</span></span>
      <div className="grow">
        <Link className="rowi-title" to={`/my/assignments/${item.id}`}>{item.title}</Link>
        <span className="meta"><span className="sr-only">{when.date}, </span>{when.range}<span className="home-invite-place">{item.location ? `, ${item.location}` : ''}</span></span>
      </div>
      {item.points_multiplier > 1 && <span className="pts"><Icon name="star"/>{multiplierLabel(item.points_multiplier)}</span>}
    </div>
    <span className="rowi-end" aria-live="polite">
      {answer === 'yes' ? <><span className="st st-ok" aria-hidden="true"><Icon name="check"/></span><span className="strong">Ты придёшь</span></>
        : answer === 'no' ? <span className="meta">Ты не придёшь</span>
        : asking ? <span className="home-invite-ask" role="group" aria-label="Точно не сможешь?" tabIndex={-1} ref={group}>
          <span className="strong" aria-hidden="true">Точно не сможешь?</span>
          <Button variant="secondary" loading={busy('/decline') || busy('/cancel')} disabled={command.isPending} onClick={() => send('no')}>Да, не смогу</Button>
          <Button variant="ghost" loading={busy('/confirm')} disabled={command.isPending} onClick={canConfirm ? () => send('yes') : () => setAsking(false)}>Я приду</Button>
        </span>
        : <>
          {canConfirm && <Button variant="secondary" loading={busy('/confirm')} disabled={command.isPending} onClick={() => send('yes')}>Я приду</Button>}
          {canDecline(item) && <Button variant="ghost" disabled={command.isPending} onClick={() => setAsking(true)}>Не смогу</Button>}
        </>}
    </span>
    {command.error && <p className="home-error" role="alert">{command.error.message}</p>}
  </div>;
}

/** The feed's own tile, so places and «Баллы ×1,5» read exactly as in «Все мероприятия». */
function Picked({cards}: {cards: EventCard[]}) {
  return <section className="sec" aria-labelledby="home-picked">
    <div className="sec-head"><h2 className="h2" id="home-picked">Подобрано для тебя</h2><Link className="quiet-link" to="/events">Все мероприятия</Link></div>
    <div className="grid-3">{cards.map(card => <EventTile key={card.occurrence_id} card={card}/>)}</div>
  </section>;
}

function Learning({learning}: {learning: ReturnType<typeof usePreparation>}) {
  const tracks = learning.data?.assignments ?? [];
  const track = tracks.find(item => !item.completed) ?? tracks[0];
  const progress = track && learningProgress(track);
  return <section className="card action-card home-learning" aria-labelledby="home-learning">
    <p className="eyebrow" id="home-learning">Обучение</p>
    {learning.isPending ? <LoadingState label="Загружаем обучение…"/>
      : learning.error ? <ErrorState error={learning.error} retry={() => {void learning.refetch();}}/>
      : track && progress ? <>
        <h2 className="h3">{track.title}</h2>
        {progress.total > 0 && <div className="row">
          <div className="bar bar-ink grow" role="progressbar" aria-label="Пройдено уроков" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}><i style={{width: `${progress.percent}%`}}/></div>
          <b className="num">{progress.done} из {progress.total}</b>
        </div>}
        <div className="actions"><Link className="btn btn-secondary" to={learningDestination(track)}>{track.completed ? 'Открыть материалы' : 'Продолжить'}</Link></div>
      </> : <>
        <h2 className="h3">Координатор подберёт материалы для твоей роли</h2>
        <div className="actions"><Link className="btn btn-secondary" to="/academy">Открыть обучение</Link></div>
      </>}
  </section>;
}

/** Level, hours and points come from the server HoursView; nothing is computed here. */
function MyPath({hours}: {hours: ReturnType<typeof useHours>}) {
  if (hours.isPending) return <section className="card mypath"><LoadingState label="Загружаем мой путь…"/></section>;
  if (hours.error) return <section className="card mypath"><ErrorState error={hours.error} retry={() => {void hours.refetch();}}/></section>;
  const {level, points} = hours.data;
  const line = pathLine(hours.data);
  return <Link className="card mypath" to="/hours" aria-labelledby="home-path">
    <p className="eyebrow" id="home-path">Мой путь</p>
    <h2 className="h2">{level.title ?? 'Первое занятие впереди'}</h2>
    <span className="mp-steps" aria-hidden="true">{level.steps.map(step => <i key={step.key} className={step.reached ? 'on' : undefined}/>)}</span>
    <span className="mp-labels">{level.steps.map(step => <span key={step.key} className={step.current ? 'cur' : undefined}>{step.title}</span>)}</span>
    {line && <span className="p">{line}</span>}
    <span className="mp-pts"><Icon name="star"/>{pointsLabel(points.balance)}</span>
  </Link>;
}
