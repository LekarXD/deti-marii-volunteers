import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type Track=components['schemas']['TrackView'];
export type AuthorLesson=components['schemas']['AuthorLessonView'];
export type Draft=NonNullable<AuthorLesson['draft']>;
export function useAuthorTracks(){return useQuery({queryKey:keys.list('learning-author'),queryFn:({signal})=>api<Track[]>('/coord/learning/tracks',{signal})});}
export function useAuthorCommand(){const client=useQueryClient();return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:'POST'|'PUT'})=>api<unknown>(`/coord/learning${path}`,{method,body,idempotencyKey:crypto.randomUUID()}),onSuccess:async()=>{await Promise.all([client.invalidateQueries({queryKey:keys.all('learning-author')}),client.invalidateQueries({queryKey:keys.all('learning-author-preview')})]);}});}
