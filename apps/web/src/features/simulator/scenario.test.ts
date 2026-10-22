import {describe,expect,it} from 'vitest';
import {cardStatus,flowOf,missingParts,passedText,queueSummary,saveProblem,splitLine,whenText} from './scenario';
import {caseTitle} from './ScenarioNewPage';
import {correctedResult} from './ReviewPage';
import {draft,queueItem,review,staff,testRun} from './fixtures.test-data';
import type {ScenarioStaff,ReviewQueueItem} from './api';

const item=(over:Record<string,unknown>={})=>staff(over) as unknown as ScenarioStaff;
describe('trainer stage without a stored status',()=>{
 it('moves a complete draft through review, test run and publication by its records',()=>{
  expect(flowOf(item({draft:{...draft,evaluation_cases:[]}})).stage).toBe('draft');
  expect(flowOf(item()).stage).toBe('review');
  expect(flowOf(item({reviews:[review(1,'changes_requested','Смягчите первую фразу')]}))).toMatchObject({stage:'draft',returned:'Смягчите первую фразу'});
  expect(flowOf(item({reviews:[review(1)]})).stage).toBe('approved');
  expect(flowOf(item({reviews:[review(1)],test_runs:[testRun(1,'running')]})).stage).toBe('approved');
  expect(flowOf(item({reviews:[review(1)],test_runs:[testRun(1,'succeeded')]})).stage).toBe('tested');
  expect(flowOf(item({version:2,publication_id:'p1',published_version:1,published_draft_version:1,reviews:[review(1)]})).stage).toBe('published');
  // an edit after publishing is a new draft revision: the old review does not cover it
  expect(flowOf(item({version:3,publication_id:'p1',published_version:1,published_draft_version:1,reviews:[review(1)]})).stage).toBe('review');
  expect(flowOf(item({version:2,publication_id:'p1',published_version:1,published_draft_version:1}),draft,true).stage).toBe('draft');
 });
 it('shows a status dot only where the card needs one',()=>{
  expect(cardStatus(item({version:2,publication_id:'p1',published_version:1,published_draft_version:1}))).toBeNull();
  expect(cardStatus(item())).toEqual({label:'у психолога',dot:'dot dot-orange'});
  expect(cardStatus(item({draft:{...draft,first_turn:''}}))).toEqual({label:'черновик',dot:'dot'});
  expect(cardStatus(item({archived_at:'2026-10-20T10:00:00Z',draft:{...draft,first_turn:''}}))).toEqual({label:'снят',dot:'dot'});
  expect(passedText(0)).toBe('ещё никто не проходил');expect(passedText(21)).toBe('21 прошёл');expect(passedText(27)).toBe('27 прошли');
 });
 it('lists what blocks approval and what blocks saving',()=>{
  expect(missingParts({...draft,first_turn:' ',evaluation_cases:[draft.evaluation_cases[0]]})).toEqual(['первая фраза','два эталона']);
  expect(missingParts({...draft,evaluation_cases:[draft.evaluation_cases[0],{...draft.evaluation_cases[1],expected_scores:{contact:0}}]})).toEqual(['оценки в эталонах']);
  expect(saveProblem({...draft,criteria:[...draft.criteria,{key:'new',title:'Новый критерий',guidance:'',critical:false}]})).toBe('Заполните критерий 3');
  expect(saveProblem(draft)).toBe('');
 });
});
describe('trainer texts',()=>{
 it('splits the stage direction from the line and titles a story by its first sentence',()=>{
  expect(splitLine('[тихо] А если я скажу?')).toEqual({dir:'тихо',text:'А если я скажу?'});
  expect(splitLine('Ты чё тут забыла?')).toEqual({dir:'',text:'Ты чё тут забыла?'});
  expect(caseTitle('На лепке мальчик ударил соседку. Она заплакала.')).toBe('На лепке мальчик ударил соседку.');
 });
 it('counts the review queue as the hero says it',()=>{
  const summary=queueSummary([queueItem('a1'),queueItem('a2',{critical:true}),queueItem('a3')] as ReviewQueueItem[],[queueItem('r1',{state:'open'})] as ReviewQueueItem[]);
  expect(summary).toMatchObject({total:4,title:'4 попытки ждут разбора',line:'2 апелляции на оценку ИИ, 1 с ошибкой в критичном и 1 просьба о поддержке'});
  expect(queueSummary([queueItem('a1')] as ReviewQueueItem[],[]).title).toBe('1 попытка ждёт разбора');
  expect(whenText('2026-10-22T08:40:00',new Date('2026-10-22T12:00:00'))).toBe('Сегодня, 08:40');
  expect(whenText('2026-10-21T16:05:00',new Date('2026-10-22T12:00:00'))).toBe('Вчера, 16:05');
 });
 it('cites a volunteer reply when the reviewer raises a zero',()=>{
  const result={summary:'Разбор ИИ',criteria:[{criterion_key:'contact',score:2 as const,explanation:'Есть контакт.',evidence:[{turn_id:'t2',quote:'рядом'}],suggestion:''},{criterion_key:'choice',score:0 as const,explanation:'Выбора не было.',evidence:[],suggestion:'Дайте выбор.'}]};
  const fixed=correctedResult(result,{choice:1},{choice:'t2',contact:'t2'},[{id:'t2',content:'Можно я посижу рядом?'}],'Выбор был, хоть и неявный.');
  expect(fixed.summary).toBe('Выбор был, хоть и неявный.');
  expect(fixed.criteria[0]).toBe(result.criteria[0]);
  expect(fixed.criteria[1]).toMatchObject({score:1,evidence:[{turn_id:'t2',quote:'Можно я посижу рядом?'}],explanation:'Специалист исправил оценку с 0 на 1 из 2.'});
 });
});
