import type {Meta,StoryObj} from '@storybook/react';
import {StudioPreviewFixture} from './StudioPreviewFixture';
import {StudioStage} from './StudioStage';
import {fictionScene,fictionPlan,fictionAsset} from './fixtures';
const meta:Meta={title:'Опора/Студия',tags:['autodocs']};export default meta;type Story=StoryObj;
export const SharedScene:Story={name:'Общая сцена live и solo',render:()=> <StudioPreviewFixture/>};
export const CameraOff:Story={name:'Камера выключена',render:()=>{const scene=fictionScene('live_event');return <StudioStage scene={scene} plan={fictionPlan(scene)} asset={fictionAsset}/>;}};
export const UnknownPrivacy:Story={name:'Неизвестная приватность блокирует кадр',render:()=>{const scene=fictionScene();return <StudioStage scene={scene} plan={{...fictionPlan(scene),privacy_state:'unknown'}} asset={fictionAsset}/>;}};
