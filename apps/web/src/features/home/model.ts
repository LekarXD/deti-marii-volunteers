import type {AssignmentParticipation} from '../activities/participationApi';
import type {Assignment as LearningAssignment} from '../learning/api';

/** Upcoming includes a class already in progress, until its actual end. */
export function upcomingAssignments(items: readonly AssignmentParticipation[], now: number) {
  return items.filter(item => ['invited', 'confirmed'].includes(item.status)
    && !item.attendance && Number.isFinite(Date.parse(item.starts_at))
    && Date.parse(item.ends_at) > now)
    .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at) || a.id.localeCompare(b.id));
}
export function assignmentWhen(item: AssignmentParticipation, now: number) {
  const zone = item.timezone;
  const day = (value: number) => new Intl.DateTimeFormat('en-CA', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(value));
  const today = day(Date.parse(item.starts_at)) === day(now);
  const date = new Intl.DateTimeFormat('ru-RU', {
    timeZone: zone, weekday: 'short', day: 'numeric', month: 'long',
  }).format(new Date(item.starts_at));
  const time = (value: string) => new Intl.DateTimeFormat('ru-RU', {
    timeZone: zone, hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
  return {today, date: today ? 'Сегодня' : date, time: `${time(item.starts_at)}–${time(item.ends_at)}`};
}
export function learningDestination(item: LearningAssignment) {
  const lesson = item.lessons.find(lesson => !lesson.completed) ?? item.lessons[0];
  if (lesson) return `/academy/lessons/${encodeURIComponent(lesson.id)}?assignment=${encodeURIComponent(item.id)}`;
  if (item.assessment_version_id) return `/academy/lessons/assessment?assignment=${encodeURIComponent(item.id)}`;
  return '/academy';
}
