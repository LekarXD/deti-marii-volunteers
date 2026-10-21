import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type Booking = components['schemas']['BookingView'];
export type StaffBooking = components['schemas']['StaffBookingView'];
export type Slot = components['schemas']['SlotView'];
export type Availability = components['schemas']['WindowView'];
export type WindowInput = components['schemas']['WindowInput'];
export const useInterviews = (staff=false) => useQuery({queryKey:keys.list('interviews',{staff}),queryFn:({signal})=>api<StaffBooking[] | Booking[]>(staff?'/api/v1/coord/interviews':'/api/v1/me/interviews',{signal}),refetchInterval:15000});
export const useAvailability = () => useQuery({queryKey:keys.all('interview-availability'),queryFn:({signal})=>api<Availability[]>('/api/v1/coord/interview-availability',{signal}),refetchInterval:15000});
export const useSlots = (from:string,to:string,timezone:string) => useQuery({queryKey:keys.list('interview-slots',{from,to,timezone}),queryFn:({signal})=>api<Slot[]>(`/api/v1/interview-slots?from=${from}&to=${to}&timezone=${encodeURIComponent(timezone)}`,{signal}),refetchInterval:10000});
export function useInterviewCommand<T=unknown>() {
  const client=useQueryClient();
  return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:'POST'|'PATCH'})=>api<T>(`/api/v1${path}`,{method,body,idempotencyKey:crypto.randomUUID()}),onSuccess:async()=>{
    await Promise.all(['interviews','interview-slots','interview-availability','application'].map(domain=>client.invalidateQueries({queryKey:keys.all(domain)})));
  }});
}
