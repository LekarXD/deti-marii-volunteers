import type {Preview} from '@storybook/react';
import {MemoryRouter} from 'react-router-dom';
import {ToastProvider} from '../src/ui';
import '../../../packages/design-tokens/tokens.css';
import '../src/app/layouts/layouts.css';
/** Isolated stories never bootstrap real user sessions or simulate successful commands. */
const preview:Preview={
 decorators:[(Story,context)=><MemoryRouter initialEntries={[context.parameters.route??'/application']}><ToastProvider><div className="dm"><div className={context.parameters.fullLayout?'':'shell'}><Story/></div></div></ToastProvider></MemoryRouter>],
 parameters:{layout:'fullscreen',backgrounds:{default:'Опора',values:[{name:'Опора',value:'#F0ECE3'},{name:'Белый',value:'#FFFFFF'}]},viewport:{viewports:{phone:{name:'390 — телефон',styles:{width:'390px',height:'844px'}},tablet:{name:'768 — планшет',styles:{width:'768px',height:'1024px'}},compact:{name:'1050 — компактный',styles:{width:'1050px',height:'900px'}},desktop:{name:'1440 — desktop',styles:{width:'1440px',height:'1000px'}}}},controls:{expanded:true}},
};
export default preview;
