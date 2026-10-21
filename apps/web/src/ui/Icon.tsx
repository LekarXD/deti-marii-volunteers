import type {SVGProps} from "react";
// Original Opora kit SVG paths, not a substitute icon family.
const paths = {
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  'chevron-left': '<path d="m15 6-6 6 6 6"/>',
  'chevron-right': '<path d="m9 6 6 6-6 6"/>',
  'check': '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  'calendar': '<rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
  'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  'chart': '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>',
  'users': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 20a6.5 6.5 0 0 0-3-5.5"/>',
  'heart': '<path d="M12 20.5s-8-4.7-8-10.6A4.4 4.4 0 0 1 12 7.3a4.4 4.4 0 0 1 8 2.6c0 5.9-8 10.6-8 10.6z"/>',
  'settings': '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  'arrow-right': '<path d="M5 12h14M13 6l6 6-6 6"/>',
  'book': '<path d="M2 4.5h6a4 4 0 0 1 4 4V21a3 3 0 0 0-3-3H2z"/><path d="M22 4.5h-6a4 4 0 0 0-4 4V21a3 3 0 0 1 3-3h7z"/>',
  'plus': '<path d="M12 5v14M5 12h14"/>',
  'search': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
} as const;
export type IconName = keyof typeof paths;
export function Icon({name,...props}:SVGProps<SVGSVGElement> & {name:IconName}) {return <svg viewBox="0 0 24 24" aria-hidden="true" {...props} className={`ic ${props.className ?? ""}`} dangerouslySetInnerHTML={{__html:paths[name]}}/>;}
