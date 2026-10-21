// One entry point for the prototype. Preserve old answers before leaving the old routes.
(function () {
  const prefix='opora-prototype-v1:';
  try {
    const old=JSON.parse(localStorage.getItem('dm-proto-v1')||'null');
    if(old?.me&&!sessionStorage.getItem(prefix+'candidate')){
      sessionStorage.setItem(prefix+'candidate',JSON.stringify(old.me));
      sessionStorage.setItem(prefix+'onboarding',JSON.stringify({done:old.done||{},best:old.test?.best??null,attempts:old.test?.attempts||0,meeting:old.meeting||null}));
    }
    if(old?.draft&&Object.keys(old.draft).length&&!sessionStorage.getItem(prefix+'apply-draft'))sessionStorage.setItem(prefix+'apply-draft',JSON.stringify({step:old.formStep||0,data:old.draft}));
  }catch(_){}
  const path=location.hash.replace(/^#\/?/,'').split('/');
  const routes={coord:'Interviews.dc.html',apply:'Apply.dc.html',home:'ApplicationStatus.dc.html',profile:'ApplicationStatus.dc.html',meet:'ApplicationStatus.dc.html',onboarding:'Onboarding.dc.html',learn:'Onboarding.dc.html',test:'Onboarding.dc.html?view=test'};
  location.replace(routes[path[0]]||'Main.dc.html');
})();
