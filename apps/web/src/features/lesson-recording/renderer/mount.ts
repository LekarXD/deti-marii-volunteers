import {SceneContractError} from '../../../../../../packages/studio-core';
import {mountRendererView} from './RendererView';
import {createRendererRuntime} from './runtime';

/** Dedicated-entry seam only. A1's private orchestrator supplies start(ticket)
 * directly in memory after verifying its launch channel; mounting makes no request. */
export function mountPrivateRenderer(element:HTMLElement) {
 const view=mountRendererView(element,{phase:'preparing',isCurrent:()=>false});
 const runtime=createRendererRuntime({render:props=>view.update(props)});let closed=false;
 return Object.freeze({
  async start(oneUseTicket:string){if(closed)throw new SceneContractError('renderer_closed');await runtime.start(oneUseTicket);},
  close(){if(!closed){closed=true;runtime.close();view.close();}},
 });
}
