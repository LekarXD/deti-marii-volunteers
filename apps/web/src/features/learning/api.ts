import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';

export type Preparation = components['schemas']['PreparationView'];
export type Assignment = components['schemas']['AssignmentView'];
export type Lesson = components['schemas']['LessonView'];
export type Attempt = components['schemas']['AttemptView'];
export type Feedback = components['schemas']['FeedbackView'];
export const learningKey = () => keys.self('learning');
export function usePreparation() {
  return useQuery({queryKey: learningKey(), queryFn: ({signal}) => api<Preparation>('/api/v1/me/preparation', {signal})});
}
export function useLesson(id?: string) {
  return useQuery({queryKey: keys.detail('learning-lesson', id??''), enabled: Boolean(id), queryFn: ({signal}) => api<Lesson>(`/api/v1/learning/lessons/${id}`, {signal})});
}
export function useAttempt(id?: string | null) {
  return useQuery({queryKey: keys.detail('learning-attempt', id??''), enabled: Boolean(id), queryFn: ({signal}) => api<Attempt>(`/api/v1/assessment-attempts/${id}/result`, {signal})});
}
export function useLearningCommand() {
  const client = useQueryClient();
  return useMutation({mutationFn: ({path, body}: {path:string;body:unknown}) => api<unknown>(`/api/v1${path}`, {method:'POST', body, idempotencyKey: crypto.randomUUID()}), onSuccess: async () => {
    await Promise.all([client.invalidateQueries({queryKey: keys.all('learning')}), client.invalidateQueries({queryKey: keys.all('learning-attempt')}),client.invalidateQueries({queryKey: keys.all('learning-tasks')})]);
  }});
}
