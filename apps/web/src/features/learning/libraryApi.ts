import {useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';

/** The fund's published materials for volunteers (GET /knowledge/library). */
export type LibraryItem=components['schemas']['LibraryItemView'];
export type LibraryText=components['schemas']['LibraryTextView'];
export type LibraryKind=LibraryItem['kind'];

export function useLibrary(){
 return useQuery({queryKey:keys.list('knowledge-library'),queryFn:({signal})=>api<LibraryItem[]>('/knowledge/library',{signal})});
}
export function useLibraryText(id?:string|null){
 return useQuery({queryKey:keys.detail('knowledge-library',id??''),enabled:Boolean(id),queryFn:({signal})=>api<LibraryText>(`/knowledge/library/${id}`,{signal})});
}
