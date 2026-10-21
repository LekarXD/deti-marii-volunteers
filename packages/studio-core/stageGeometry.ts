/** Pure Opora stage geometry, ported from pinned OD stageGeometry.js.
 * Source algorithms preserved for side/overlay; arch visual shape and local mobile reflow omitted. */
import {CAMERA_SIZE} from './constants';
import type {Rect,Geometry,GeometryOptions} from './types';
import { pipGeometry, smallStage } from './cameraLayout';

/** Inside the scene card: around the slide and the camera, and between them. */
export const PAD = 16;
export const GAP = 16;
/** A learner's line in the card under the slide (replaces the bottom padding). */
export const FOOT = 36;
/** A phone held upright: the presenter's band under the slide. */
export const BAND = 92;
const PIP_INSET = 14;

/** The arch's (column's) width per unit of the slide's height: 22 → 0.57, 28 → 0.75 (3 : 4), 36 → 0.99. */
export function presenterShape(cameraSize:number) {
    return 0.75 + (cameraSize - CAMERA_SIZE.initial) * 0.03;
}

const rect = (x:number, y:number, w:number, h:number):Rect => ({ x: Math.round(x), y: Math.round(y), w: Math.max(0, Math.round(w)), h: Math.max(0, Math.round(h)) });
/** Content of `ratio` fitted whole into w × h. */
const fit = (ratio:number, w:number, h:number) => { const height = Math.max(0, Math.min(h, w / ratio)); return { w: height * ratio, h: height }; };

function placeAll({ stageW, stageH, occlude = 0, ratio = 16 / 9, layout = 'side', cameraSize = CAMERA_SIZE.initial,
    folded = false, camera = true, compact = false, foot = 0, band = false, corner = 'br' }:GeometryOptions):Geometry {
    const visible = Math.max(0, stageW - occlude);
    if (band) {
        const area = fit(ratio, visible, stageH - BAND);
        const content = rect((visible - area.w) / 2, 0, area.w, area.h);
        return { mode: 'band', visible, content, scene: rect(0, 0, visible, stageH), band: rect(0, stageH - BAND, visible, BAND) };
    }
    const bottom = foot || PAD;
    const freeW = Math.max(0, visible - 2 * PAD);
    const freeH = Math.max(0, stageH - PAD - bottom);
    // The card around the content (and the camera beside it): centred in what the viewer sees.
    const card = (w:number, h:number) => {
        const x = (visible - w - 2 * PAD) / 2, y = (stageH - h - PAD - bottom) / 2;
        return rect(x, y, w + 2 * PAD, h + PAD + bottom);
    };
    const withFoot = (content:Rect) => (foot ? rect(content.x, content.y + content.h, content.w, foot) : null);
    if (!camera) {
        const area = fit(ratio, freeW, freeH);
        const scene = card(area.w, area.h);
        const content = rect(scene.x + PAD, scene.y + PAD, area.w, area.h);
        return { mode: 'none', visible, scene, content, foot: withFoot(content) };
    }
    if (layout === 'overlay' || smallStage(stageW, stageH, compact)) {
        const { width } = pipGeometry({ stageW, stageH, occlude, ratio, cameraSize, folded, compact });
        const height = width * 9 / 16;
        const area = fit(ratio, freeW, freeH);
        const room = width + GAP;
        const beside = !folded && freeW - area.w >= room;
        const left = corner.endsWith('l');
        const top = corner.startsWith('t');
        const scene = card(area.w + (beside ? room : 0), area.h);
        const content = rect(scene.x + PAD + (beside && left ? room : 0), scene.y + PAD, area.w, area.h);
        const x = beside ? (left ? content.x - room : content.x + content.w + GAP)
            : (left ? content.x + PIP_INSET : content.x + content.w - PIP_INSET - width);
        const y = beside ? (top ? content.y : content.y + content.h - height)
            : (top ? content.y + PIP_INSET : content.y + content.h - PIP_INSET - height);
        return { mode: 'window', visible, scene, content, foot: withFoot(content), pip: { ...rect(x, y, width, height), beside } };
    }
    const k = presenterShape(cameraSize);
    const h = Math.max(0, Math.min(freeH, (freeW - GAP) / (ratio + k)));
    const scene = card(h * ratio + GAP + h * k, h);
    const content = rect(scene.x + PAD, scene.y + PAD, h * ratio, h);
    const arch = rect(content.x + content.w + GAP, content.y, h * k, content.h);
    return { mode: 'column', visible, scene, content, camera: arch, foot: withFoot(content) };
}

/** «Крупнее / Мельче»: every step visibly widens or narrows the arch (the window). */
export function sizeSteps(cameraSize:number) {
    const { min, max, step } = CAMERA_SIZE;
    return {
        smaller: cameraSize > min ? Math.max(min, cameraSize - step) : null,
        larger: cameraSize < max ? Math.min(max, cameraSize + step) : null,
        smallerTip: 'Мельче некуда',
    };
}

const shift = (box:Rect|undefined|null, m:number) => (box ? { ...box, x: box.x + m, y: box.y + m } : box);
/**
 * The layout, with `margin` of the room's background around it (fullscreen: the cards never touch the
 * screen's edges). Everything else — see placeAll.
 */
export function stageGeometry({ margin = 0, ...options }:GeometryOptions):Geometry {
    if(options.layout==='camera_only') {const width=Math.max(0,options.stageW-2*margin),height=Math.max(0,options.stageH-2*margin);return {mode:'camera_only',visible:width,scene:rect(margin,margin,width,height),content:rect(0,0,0,0),camera:rect(margin+width*.27,margin+height*.08,width*.46,height*.8)};}
    if (!margin) return placeAll(options);
    const geo = placeAll({ ...options, stageW: Math.max(0, options.stageW - 2 * margin), stageH: Math.max(0, options.stageH - 2 * margin) });
    return Object.fromEntries(Object.entries(geo).map(([key, value]) => [key, value && typeof value === 'object' && 'x' in value ? shift(value as Rect, margin) : value])) as Geometry;
}

