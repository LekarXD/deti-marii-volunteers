/** Ported OD cameraLayout.js pure sizing helpers. No provider or visual skin. */
import {CAMERA_SIZE} from './constants';
import type {GeometryOptions} from './types';
const clamp = (value:number, min:number, max:number) => Math.max(min, Math.min(max, value));

/** Below this stage width (a phone held upright) every layout is «Окошко»: a slide must stay readable. */
export const SMALL_STAGE = 560;
/** On a phone or a tablet (`compact`) a stage lower than this — a phone on its side, a tablet held upright — is small too. */
export const LOW_STAGE = 440;

/** The camera field would leave the slide too little of this stage: the camera becomes a corner window. */
export function smallStage(stageW:number, stageH:number, compact = false) {
    return stageW > 0 && (stageW < SMALL_STAGE || (compact && stageH > 0 && stageH < LOW_STAGE));
}
/** Between the content and the camera field, and around the camera of «Колонка». */
export const FIELD_GAP = 12;
const PIP = { min: 120, max: 400, gap: 14 };

/** The camera field's least share of the visible stage: 22 → 18 %, 28 → 30 %, 36 → 46 %. */
export function fieldShare(cameraSize:number) {
    return 0.3 + (cameraSize - CAMERA_SIZE.initial) * 0.02;
}

/**
 * «Окошко»: the corner window, a 16:9 frame. Its width follows the presenter's size
 * (22 → 13 % of the stage, 28 → 17 %, 36 → 22 %). Content is fitted into what the
 * viewer actually sees — a drawer over the stage's edge (`occlude`) takes its width
 * away — and when the content leaves enough empty margin at the side, the window
 * moves into that margin (`beside`) instead of covering a slide.
 */
export function pipGeometry({ stageW, stageH, occlude = 0, ratio = 16 / 9, cameraSize = CAMERA_SIZE.initial, folded = false, compact = false }:GeometryOptions) {
    // A phone's stage is ~360 px wide: the window shrinks with it so a slide stays readable.
    const narrow = smallStage(stageW, stageH);
    // A phone on its side: the window is low enough to step into the margin beside a 16:9 slide.
    const low = !narrow && smallStage(stageW, stageH, compact);
    const min = narrow || low ? Math.round(PIP.min * 0.62) : PIP.min;
    const max = narrow ? Math.max(min, Math.round(stageW * 0.22)) : low ? Math.max(min, Math.round(stageH * 0.3)) : PIP.max;
    const width = clamp(Math.round(stageW * cameraSize * 0.006), min, max);
    const visible = Math.max(0, stageW - occlude);
    const fitted = Math.min(visible, stageH * ratio);
    const room = width + PIP.gap * 2;
    const beside = !folded && stageW > 0 && visible - fitted >= room ? room : 0;
    return { width, beside };
}

