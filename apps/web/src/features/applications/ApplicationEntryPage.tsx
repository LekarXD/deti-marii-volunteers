import {Navigate} from 'react-router-dom';
import {ErrorState,LoadingState} from '../../ui';
import {ApiError} from '../../api/transport';
import {useApplication} from './api';
/** Entry follows the current server owner; a contact string never chooses an account. */
export function ApplicationEntryPage(){
  const application=useApplication();
  if(application.isPending)return <LoadingState label="Открываем ваш кабинет…"/>;
  if(application.data)return <Navigate to="/application" replace/>;
  if(application.error instanceof ApiError&&application.error.status===404)return <Navigate to="/apply" replace/>;
  return <ErrorState error={application.error} retry={()=>void application.refetch()}/>;
}
