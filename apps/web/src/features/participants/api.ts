import {api} from '../../api/transport';
import type {components} from '../../api/generated/schema';
export type Participant = components['schemas']['SafeParticipant'];
export type ParticipantInput = components['schemas']['ParticipantInput'];
export type Group = components['schemas']['GroupView'];
export type GroupInput = components['schemas']['GroupInput'];
export type GroupDetail = components['schemas']['GroupDetail'];
export type PrivateNote = components['schemas']['PrivateNoteView'];
export type Membership = components['schemas']['GroupMember'];
export const readParticipants = (query = '', archived = false, signal?: AbortSignal, offset=0) => api<components['schemas']['ParticipantList']>(`/coord/participants?query=${encodeURIComponent(query)}&archived=${archived}&offset=${offset}`, {signal});
export const readParticipant = (id: string, signal?: AbortSignal) => api<Participant>(`/coord/participants/${id}`, {signal});
export const readGroups = (signal?: AbortSignal, archived=false) => api<components['schemas']['GroupList']>(`/coord/groups?archived=${archived}`, {signal});
export const readGroup = (id: string, at: string, signal?: AbortSignal) => api<GroupDetail>(`/coord/groups/${id}?at=${at}`, {signal});
export const readStaff = (signal?: AbortSignal) => api<components['schemas']['ParticipantStaffOptions']>('/coord/groups/staff-options', {signal});
export const readNotes = (id: string, signal?: AbortSignal) => api<components['schemas']['PrivateNoteList']>(`/coord/participants/${id}/private-notes`, {signal});
export const readAssignmentParticipants = (id: string, signal?: AbortSignal) => api<components['schemas']['AssignmentParticipantList']>(`/me/assignments/${id}/participants`, {signal});
export const command = <T,>(path: string, body: unknown, method = 'POST') => api<T>(path, {method, body, idempotencyKey: crypto.randomUUID()});

export async function uploadPhoto(file: File): Promise<string> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) throw new Error('Выберите PNG, JPEG или WebP до 5 МБ.');
  const checksum = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer())), v => v.toString(16).padStart(2, '0')).join('');
  const asset = await command<{id: string}>('/assets/upload-intents', {content_type: file.type, expected_size: file.size, checksum});
  for (let offset=0; offset<file.size; offset+=1024*1024) {
    await api(`/assets/${asset.id}/upload`, {method:'PATCH', body:file.slice(offset,offset+1024*1024), headers:{'X-Upload-Offset':String(offset),'Content-Type':'application/octet-stream'}});
  }
  await command(`/assets/${asset.id}/complete-upload`, {});
  return asset.id;
}
