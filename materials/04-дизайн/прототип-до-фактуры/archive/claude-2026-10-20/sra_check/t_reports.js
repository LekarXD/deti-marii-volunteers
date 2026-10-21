module.exports = (C, V) => {
  let v = V();
  console.log('tabs', v.tabs.map(t=>t.label+(t.cls?'*':'')).join(' | '), '| checked', v.checkedLabel);
  v.nums[2].toggle(); v = V(); console.log('after tick', v.checkedLabel);
  v.secs[0].accept(); v = V(); console.log('sec accepted', v.secs[0].tag, v.checkedLabel);
  v.secs[1].toggleEdit(); v = V(); console.log('editing', v.secs[1].editing); v.secs[1].type({target:{value:'X'}}); v = V(); console.log('text', v.secs[1].text);
  v.secs[2].toggleEdit(); v = V(); console.log('stories edit', v.secs[2].stories.map(y=>y.editing+':'+y.tagLabel));
  v.secs[2].stories[1].ask(); v = V(); console.log('asked', v.secs[2].stories[1].tagLabel, v.secs[2].stories[1].canAsk);
  v.dlWord(); v = V(); console.log(v.dlText, v.dlCls);
  v.tabs[1].pick(); v = V(); console.log('letters', v.isLetters, v.letterTitle, v.letterText.slice(0,60));
  v.occs[2].pick(); v = V(); v.tones[1].pick(); v = V(); console.log('uni off:', v.letterTitle, v.letterText.slice(0,80));
  v.toggleLetterEdit(); v = V(); v.typeLetter({target:{value:'Мой текст'}}); v = V(); console.log('custom', v.letterText, v.letterEditing);
  v.send(); v = V(); console.log('sent', v.sent, v.letterEditing);
  v.setVol({target:{value:'as'}}); v = V(); console.log('anna', v.isAs, v.certHours, v.certPeriod);
  v.tabs[2].pick(); v = V(); console.log('weekly', v.toLine, v.chanLine);
  v.recips[2].toggle(); v = V(); v.chans[1].pick(); v = V(); v.incs[0].toggle(); v = V(); console.log(v.toLine, v.chanLine, v.incNums);
  v.save(); v = V(); console.log('saved', v.saved);
};
