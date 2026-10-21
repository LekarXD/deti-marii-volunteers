module.exports = (C, V) => {
  let v = V(); v.modes[1].pick();
  for (let i = 0; i < 5; i++) { v = V(); const c = v.checks[i]; if (!c.on) c.toggle(); }
  v = V(); console.log('all checked:', v.protoDone, v.closeDis, v.closeBlocked);
  v.closeCase(); v = V(); console.log('closed:', v.caseClosed, v.caseTag, v.log.length);
  v.modes[0].pick(); v = V(); console.log('coord urgent:', v.urgentDot, v.urgentStatus);
};
