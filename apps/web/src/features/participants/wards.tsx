import {appPath} from '../../basePath';
import {Icon, cx, type IconName} from '../../ui';
import type {Participant, WardGroup} from './api';

/** Shared pieces of the coordinator «Подопечные» pages and the volunteer memo card. */
type Person = Pick<Participant,'id'|'display_name'|'photo_asset_id'>;
type TagField = 'communication_tags'|'support_tags'|'interests_tags';
type NoteField = 'communication'|'support'|'interests';
export const MEMO_TAGS_MAX = 12, MEMO_TAG_LENGTH = 40;

export const plural = (n:number, [one, few, many]:[string,string,string]) => {const a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;};
export const thisYear = () => Number(new Intl.DateTimeFormat('en', {year:'numeric', timeZone:'Europe/Moscow'}).format(new Date()));
/** «12 лет» from the birth year; empty when the year is unknown or not plausible. */
export function ageLabel(birthYear?:number|null, year = thisYear()) {
  if (!birthYear || birthYear < 1900 || birthYear >= year) return '';
  const n = year - birthYear;
  return `${n} ${plural(n, ['год', 'года', 'лет'])}`;
}
/** Two letters from the name; bracketed labels such as «[ДЕМО]» and punctuation never become an initial. */
export function initials(name:string) {
  const first = (word:string) => word.match(/\p{L}/u)?.[0] ?? '';
  const words = name.replace(/\[[^\]]*\]|\([^)]*\)/g, ' ').split(/\s+/).map(first).filter(Boolean);
  const letters = (words.length ? words : [first(name)]).slice(0, 2).join('');
  return letters ? letters.toLocaleUpperCase('ru') : '?';
}
const tones = ['o', 'b', 'g', 'v', 'p'];
export const toneOf = (id:string) => tones[[...id].reduce((sum, c) => (sum * 31 + c.charCodeAt(0)) >>> 0, 0) % tones.length];
export const groupsLine = (groups:WardGroup[] = []) => groups.map(g => g.title).join(', ');
export const wardLine = (birthYear:number|null|undefined, groups?:WardGroup[]) => [ageLabel(birthYear), groupsLine(groups)].filter(Boolean).join(', ');

export const memoBlocks:{tags:TagField;note:NoteField;title:string;art:string;icon:IconName;presets:string[]}[] = [
  {tags:'communication_tags', note:'communication', title:'Как общаться', art:'art-b', icon:'message', presets:['Говорить коротко и спокойно', 'Давать время ответить', 'Показывать, а не объяснять', 'Не трогать без спроса', 'Понимает жесты', 'Говорит мало, понимает много']},
  {tags:'support_tags', note:'support', title:'Какая поддержка нужна', art:'art-g', icon:'hand', presets:['Помочь с ножницами и клеем', 'Сопровождать при переходах', 'Тихий угол при перегрузке', 'Напоминать про перерыв', 'Держать рядом наушники']},
  {tags:'interests_tags', note:'interests', title:'Интересы', art:'art-y', icon:'star', presets:['Рисование', 'Музыка', 'Лепка', 'Машинки', 'Животные', 'Танцы']},
];

export const wardPhotoUrl = (person:Person, assignmentId?:string) => !person.photo_asset_id ? '' : appPath(assignmentId ? `/api/v1/me/assignments/${assignmentId}/participants/${person.id}/photo` : `/api/v1/coord/participants/${person.id}/photo`);

/** Photo or initials in the canvas sizes: sm 44, md 56, lg 88, xl 184. `alt` empty keeps the image decorative. */
export function WardPhoto({person, size = 'md', src, alt = '', assignmentId, className}:{person:Person;size?:'sm'|'md'|'lg'|'xl';src?:string;alt?:string;assignmentId?:string;className?:string}) {
  const url = src ?? wardPhotoUrl(person, assignmentId);
  const cls = cx('ward-ph', size !== 'md' && `ward-ph-${size}`, className);
  return url ? <img className={cls} src={url} alt={alt}/> : <span className={cx(cls, `ward-ph-${toneOf(person.id)}`)} aria-hidden="true">{initials(person.display_name)}</span>;
}

export const MemoIcon = ({icon, art, className}:{icon:IconName;art:string;className?:string}) => <span className={cx('art', art, className)} aria-hidden="true"><Icon name={icon}/></span>;
export function MemoTags({tags, empty = 'Пока пусто'}:{tags:string[];empty?:string}) {
  return tags.length ? <div className="ward-memo-tags">{tags.map(tag => <span key={tag}>{tag}</span>)}</div> : <p className="meta">{empty}</p>;
}
type Memo = Partial<Record<TagField, string[]>> & Partial<Record<NoteField, string>>;
/** «Как помочь на занятии»: three memo cards with chips and the optional short note. */
export function MemoCards({person}:{person:Memo}) {
  return <div className="grid-3">{memoBlocks.map(block => {
    const tags = person[block.tags] ?? [], note = person[block.note]?.trim();
    return <div className="card ward-memo" key={block.tags}>
      <div className="ward-memo-head"><MemoIcon icon={block.icon} art={block.art}/><h3 className="h3">{block.title}</h3></div>
      {(tags.length > 0 || !note) && <MemoTags tags={tags} empty="Памятка уточняется."/>}
      {note && <p className="ward-memo-note">{note}</p>}
    </div>;
  })}</div>;
}
