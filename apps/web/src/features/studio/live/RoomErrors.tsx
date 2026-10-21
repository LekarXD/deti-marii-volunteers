import {ErrorState} from '../../../ui';
/** One recovery message per distinct visible failure, even when a command also
 * reaches the room action's catch. Every independent failure remains visible. */
export function RoomErrors({errors,retry}:{errors:readonly unknown[];retry:()=>void}) {
 const messages=new Set<string>();
 for(const error of errors){
  if(!error)continue;
  messages.add(typeof error==='string'?error:error instanceof Error?error.message:'Проверьте соединение и попробуйте ещё раз.');
 }
 return <>{[...messages].map(message=><ErrorState key={message} error={new Error(message)} retry={retry}/>)}</>;
}
