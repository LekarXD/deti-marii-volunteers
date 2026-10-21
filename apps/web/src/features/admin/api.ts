import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import type {components} from '../../api/generated/schema';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
type S=components['schemas'];
export type Directory=S['StaffDirectoryView'];
export type Member=S['StaffMemberView'];
export type Catalog=S['StaffPermissionCatalogView'];
export type Scope=S['StaffScopeOptionView'];
export type StaffUser=S['StaffUserOptionView'];
export type Invitation=S['StaffInvitationView'];
export type Selection=S['StaffPermissionSelection'];
export function useAdminQuery<T>(name:string,path:string,enabled=true){return useQuery({queryKey:keys.list('admin',{name,path}),queryFn:({signal})=>api<T>(path,{signal}),enabled,refetchInterval:20000});}
export function useAdminCommand(){const cache=useQueryClient(),receipt=useRef({signature:'',key:''});return useMutation({mutationFn:({path,body}:{path:string;body:unknown})=>{const signature=JSON.stringify([path,body]);if(receipt.current.signature!==signature)receipt.current={signature,key:crypto.randomUUID()};return api<unknown>(path,{method:'POST',body,idempotencyKey:receipt.current.key,retries:0});},onSuccess:async()=>{await cache.invalidateQueries({queryKey:keys.all('admin')});},onError:async error=>{if(error instanceof ApiError&&error.status===409)await cache.invalidateQueries({queryKey:keys.all('admin')});}});}
