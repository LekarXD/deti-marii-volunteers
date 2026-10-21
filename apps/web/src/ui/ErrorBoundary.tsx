import {Component,type ErrorInfo,type ReactNode} from 'react';
import {Button} from './controls';
/** Isolates feature failures; permits one explicit recovery reload per build. */
export class ErrorBoundary extends Component<{children:ReactNode},{error:Error|null}> {
 state:{error:Error|null}={error:null};
 static getDerivedStateFromError(error:Error){return {error};}
 componentDidCatch(_error:Error,_info:ErrorInfo){/* Report only through configured private telemetry. */}
 render(){if(!this.state.error)return this.props.children;return <main className="dm empty" role="alert"><h1 className="h2">Не удалось открыть страницу</h1><p className="p">Изменения могли обновить приложение. Попробуйте загрузить страницу ещё раз.</p><Button onClick={()=>window.location.reload()}>Обновить страницу</Button></main>;}
}
