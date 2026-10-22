import {addDays, labelDate, labelTime, localParts} from '../activities/calendarDates';
import {awaitingCoordinator, type AssignmentParticipation} from '../activities/participationApi';
import type {EventFeed} from '../activities/eventsApi';
import type {Assignment as LearningAssignment} from '../learning/api';
import type {Preparation} from '../followups/api';
import {hoursLabel, type Hours} from '../profile/api';
import {firstNameOf, initialsOf} from '../../ui/names';

/** Upcoming includes a class already in progress, until its actual end. */
export function upcomingAssignments(items: readonly AssignmentParticipation[], now: number) {
  return items.filter(item => ['invited', 'confirmed'].includes(item.status)
    && item.occurrence_status === 'scheduled' && !item.attendance && Number.isFinite(Date.parse(item.starts_at))
    && Date.parse(item.ends_at) > now)
    .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at) || a.id.localeCompare(b.id));
}
/** A self sign-up waiting for the coordinator has nothing to answer, so it never takes the hero. */
export function answerable(items: readonly AssignmentParticipation[]) {
  return items.filter(item => !awaitingCoordinator(item));
}

const capital = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
type When = Pick<AssignmentParticipation, 'starts_at' | 'ends_at' | 'timezone'>;
/** Dates and times in the event's own timezone; «today» also covers a class already in progress. */
export function assignmentWhen(item: When, now: number) {
  const start = localParts(item.starts_at, item.timezone).date;
  const sameDay = start === localParts(new Date(now).toISOString(), item.timezone).date;
  const running = Date.parse(item.starts_at) <= now && now < Date.parse(item.ends_at);
  const time = labelTime(item.starts_at, item.timezone);
  return {
    today: sameDay || running,
    date: sameDay ? 'Сегодня' : capital(labelDate(start, {weekday: 'short', day: 'numeric', month: 'long'})),
    /** «24 октября» or «сегодня», for a sentence. */
    day: sameDay ? 'сегодня' : labelDate(start),
    time,
    range: `${time}–${labelTime(item.ends_at, item.timezone)}`,
    dayNumber: String(Number(start.slice(8))),
    weekday: labelDate(start, {weekday: 'short'}),
  };
}

export type HeroKind = 'today' | 'invitation' | 'nearest';
export function heroKind(item: AssignmentParticipation, now: number): HeroKind {
  if (item.status === 'invited') return 'invitation';
  return assignmentWhen(item, now).today ? 'today' : 'nearest';
}
export function heroEyebrow(kind: HeroKind, newbie: boolean) {
  if (kind === 'today') return 'Сегодня';
  if (newbie) return 'Твой первый выход';
  return kind === 'invitation' ? 'Тебя приглашают' : 'Ближайшее занятие';
}

/** «Анна» from «Анна Смирнова»; the account placeholder «Волонтёр» is not a name. */
export function firstName(displayName?: string | null) {
  const name = firstNameOf(displayName);
  return name === 'Волонтёр' ? '' : name;
}
export function initials(displayName: string) {
  return initialsOf(displayName);
}
/** The server lists the group's leader first, then the coordinator. */
export function meetingContact(preparation?: Preparation) {
  return preparation?.contacts[0];
}
export function coordinatorContact(preparation?: Preparation) {
  return preparation?.contacts.find(contact => contact.role === 'Координатор');
}

/** The «Опаздываю» notice is an ordinary question to the coordinator; once sent it stays visible. */
export const LATE_TEXT = 'Опаздываю на занятие';
export function lateSent(preparation?: Preparation) {
  return Boolean(preparation?.questions.some(question => question.text === LATE_TEXT));
}

export type PathStep = {title: string; text: string; state: '' | 'done' | 'now'};
/** First weeks of a newcomer: an invitation waits on step 2, a confirmed first exit is step 3. */
export function startPath(status: string, leader = '', coordinator = ''): PathStep[] {
  const current = status === 'invited' ? 1 : 2;
  const steps: [string, string][] = [
    ['Встреча с координатором', 'Роль подобрали'],
    ['Подтверждение', current > 1 ? 'Ты придёшь' : 'Ответь, придёшь ли'],
    ['Первый выход', `${leader || 'Ведущий'} рядом всё занятие`],
    ['Разговор после', `${coordinator || 'Координатор'} позвонит`],
    ['Следующий шаг', 'Регулярно, другая роль или пауза'],
  ];
  return steps.map(([title, text], index) => ({title, text, state: index < current ? 'done' : index === current ? 'now' : ''}));
}

/** Server order; only events still open to this volunteer and not already theirs. */
export function pickedEvents(feed?: EventFeed) {
  if (!feed?.can_sign_up) return [];
  return feed.items.filter(card => !card.full && !card.conflict && !card.my_assignment && !card.my_reserve).slice(0, 3);
}

/** Level copy straight from HoursView.level; the client never computes a level. */
export function pathLine(hours: Pick<Hours, 'level' | 'total_minutes'>) {
  const {level, total_minutes: total} = hours;
  if (!level.title) return level.next_title ? `Уровень «${level.next_title}» откроется после первого занятия` : '';
  const help = `${hoursLabel(total)} помощи`;
  return level.next_title && level.next_minutes != null ? `${help}, до «${level.next_title}» ${hoursLabel(level.next_minutes - total, true)}` : help;
}

export function learningProgress(item: LearningAssignment) {
  const total = item.lessons.length, done = item.lessons.filter(lesson => lesson.completed).length;
  return {done, total, percent: total ? Math.round(done / total * 100) : 0};
}
export function learningDestination(item: LearningAssignment) {
  const lesson = item.lessons.find(lesson => !lesson.completed) ?? item.lessons[0];
  if (lesson) return `/academy/lessons/${encodeURIComponent(lesson.id)}?assignment=${encodeURIComponent(item.id)}`;
  if (item.assessment_version_id) return `/academy/lessons/assessment?assignment=${encodeURIComponent(item.id)}`;
  return '/academy';
}

/** A newcomer has no confirmed занятие that already ended; the past year of the schedule answers that. */
export function homePastRange(now: number) {
  const to = localParts(new Date(now).toISOString()).date;
  return {from: addDays(to, -366), to};
}
export function hadConfirmedPast(items: readonly AssignmentParticipation[], now: number) {
  return items.some(item => item.status === 'confirmed' && item.occurrence_status !== 'cancelled' && Date.parse(item.ends_at) <= now);
}

/** Ninety inclusive Moscow calendar days; the API includes overlapping overnight events. */
export function homeScheduleRange(now: number) {
  const from = localParts(new Date(now).toISOString()).date;
  return {from, to: addDays(from, 89)};
}
