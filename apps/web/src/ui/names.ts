/** Name words without service marks such as «[ДЕМО]». */
export function nameWords(name?:string|null){return (name??'').trim().split(/\s+/).filter(word=>word&&!/^\[.*\]$/.test(word));}
/** «Анна» from «Анна Смирнова». */
export function firstNameOf(name?:string|null){return nameWords(name)[0]??'';}
/** «АС» from «Анна Смирнова». */
export function initialsOf(name?:string|null){return nameWords(name).slice(0,2).map(word=>word.charAt(0).toUpperCase()).join('');}
