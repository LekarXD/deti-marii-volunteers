import {useMutation, useQuery, useQueryClient, type QueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type Track=components['schemas']['TrackView'];
export type AuthorLesson=components['schemas']['AuthorLessonView'];
export type Draft=NonNullable<AuthorLesson['draft']>;
export type Webinar=components['schemas']['WebinarView'];
type Method='POST'|'PUT'|'PATCH';
export function useAuthorTracks(){return useQuery({queryKey:keys.list('learning-author'),queryFn:({signal})=>api<Track[]>('/coord/learning/tracks',{signal})});}
export function useAuthorCommand(){const client=useQueryClient();return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:Method})=>api<unknown>(`/coord/learning${path}`,{method,body,idempotencyKey:crypto.randomUUID()}),onSuccess:async()=>{await Promise.all([client.invalidateQueries({queryKey:keys.all('learning-author')}),client.invalidateQueries({queryKey:keys.all('learning-author-preview')})]);}});}
/** Puts a fresh course straight into the list, so the next command already sends its new version. */
export function putTrack(client:QueryClient,track:Track){client.setQueryData<Track[]>(keys.list('learning-author'),list=>list?.map(item=>item.id===track.id?track:item));}
/** Same for one lesson: autosave must not refetch every course on each pause in typing. */
export function putLesson(client:QueryClient,lesson:AuthorLesson){client.setQueryData<Track[]>(keys.list('learning-author'),list=>list?.map(track=>track.id===lesson.track_id?{...track,lessons:track.lessons.map(item=>item.id===lesson.id?lesson:item)}:track));}
export function useTrackCommand(){const client=useQueryClient();return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:Method})=>api<Track>(`/coord/learning${path}`,{method,body,idempotencyKey:crypto.randomUUID()}),onSuccess:track=>{putTrack(client,track);void client.invalidateQueries({queryKey:keys.all('learning-author')});}});}
export function useUpcomingWebinars(){return useQuery({queryKey:keys.list('learning-webinars'),queryFn:({signal})=>api<Webinar[]>('/webinars',{signal}),retry:false});}
