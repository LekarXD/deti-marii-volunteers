// Native disclosures with one open menu, keyboard navigation and outside dismissal.
(()=>{
 const menus=()=>[...document.querySelectorAll('details[name="coord-navigation"]')];
 const close=(except)=>menus().forEach(menu=>{if(menu!==except)menu.open=false;});
 document.addEventListener('click',event=>{const menu=event.target.closest('details[name="coord-navigation"]');close(menu);},true);
 document.addEventListener('focusin',event=>{const menu=event.target.closest('details[name="coord-navigation"]');close(menu);},true);
 document.addEventListener('keydown',event=>{
  const menu=event.target.closest('details[name="coord-navigation"]');
  if(!menu)return;
  const summary=menu.querySelector('summary');
  if(event.key==='Escape'){event.preventDefault();menu.open=false;summary.focus();return;}
  const links=[...menu.querySelectorAll('a[href]')].filter(a=>a.getClientRects().length);
  if(event.target===summary&&['ArrowDown','ArrowUp'].includes(event.key)){
   event.preventDefault();close(menu);menu.open=true;
   const all=[...menu.querySelectorAll('a[href]')];(event.key==='ArrowUp'?all.at(-1):all[0])?.focus();return;
  }
  if(!links.includes(event.target))return;
  let index=links.indexOf(event.target);
  if(event.key==='ArrowDown')index=(index+1)%links.length;
  else if(event.key==='ArrowUp')index=(index-1+links.length)%links.length;
  else if(event.key==='Home')index=0;
  else if(event.key==='End')index=links.length-1;
  else return;
  event.preventDefault();links[index].focus();
 });
})();
