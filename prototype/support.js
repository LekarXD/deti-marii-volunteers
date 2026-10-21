// Local preview stand-in for the .dc.html runtime: holes, sc-if, sc-for, events, DCLogic.
// Scratchpad only — never shipped with the canvas.
(function () {
  var supportBase = document.currentScript ? new URL(".", document.currentScript.src) : new URL(".", location.href);
  function load(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement('script'); s.src = new URL(src, supportBase).href; s.onload = res; s.onerror = rej; document.head.appendChild(s);
    });
  }
  var ready = load('./vendor/react.production.min.js')
    .then(function () { return load('./vendor/react-dom.production.min.js'); });

  var EVENTS = { onclick: 'onClick', onchange: 'onChange', onsubmit: 'onSubmit', onkeydown: 'onKeyDown', oninput: 'onInput', onblur: 'onBlur', onfocus: 'onFocus' };
  var RENAME = { 'class': 'className', 'for': 'htmlFor', tabindex: 'tabIndex', maxlength: 'maxLength', minlength: 'minLength', readonly: 'readOnly', autocomplete: 'autoComplete', autofocus: 'autoFocus', viewbox: 'viewBox' };
  var HOLE = /\{\{\s*([^}]+?)\s*\}\}/g;
  window.__dcErrors = [];

  function lookup(path, scope) {
    path = path.trim();
    if (path === 'true') return true;
    if (path === 'false') return false;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    if (!/^[$\w]+(\.[$\w]+)*$/.test(path)) { window.__dcErrors.push('bad hole: ' + path); return undefined; }
    var v = path.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, scope);
    if (v === undefined) window.__dcErrors.push('undefined hole: ' + path);
    return v;
  }
  function interp(str, scope) {
    var whole = str.match(/^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/);
    if (whole) return lookup(whole[1], scope);
    return str.replace(HOLE, function (m, p) { var v = lookup(p, scope); return v == null ? '' : String(v); });
  }
  function styleObj(str) {
    var o = {};
    String(str || '').split(';').forEach(function (part) {
      var i = part.indexOf(':'); if (i < 0) return;
      var k = part.slice(0, i).trim(); var v = part.slice(i + 1).trim(); if (!k) return;
      if (k.indexOf('--') !== 0) k = k.replace(/-([a-z])/g, function (m, c) { return c.toUpperCase(); });
      o[k] = v;
    });
    return o;
  }

  function conv(node, scope, key) {
    var R = window.React;
    if (node.nodeType === 3) {
      var t = node.nodeValue;
      return t.indexOf('{{') >= 0 ? interp(t, scope) : t;
    }
    if (node.nodeType !== 1) return null;
    var tag = node.tagName.toLowerCase();
    if (tag === 'helmet' || tag === 'script') return null;
    var kids = function (sc) { return Array.prototype.map.call(node.childNodes, function (c, i) { return conv(c, sc, i); }); };
    if (tag === 'sc-if') {
      var v = interp(node.getAttribute('value') || '', scope);
      return v ? R.createElement(R.Fragment, { key: key }, kids(scope)) : null;
    }
    if (tag === 'sc-for') {
      var list = interp(node.getAttribute('list') || '', scope) || [];
      var as = node.getAttribute('as') || 'item';
      return R.createElement(R.Fragment, { key: key }, list.map(function (item, i) {
        var sc = Object.assign({}, scope); sc[as] = item; sc.$index = i;
        return R.createElement(R.Fragment, { key: i }, kids(sc));
      }));
    }
    var props = { key: key };
    Array.prototype.forEach.call(node.attributes, function (a) {
      var name = a.name;
      if (name.indexOf('hint-') === 0) return;
      var val = a.value.indexOf('{{') >= 0 ? interp(a.value, scope) : a.value;
      if (EVENTS[name]) { props[EVENTS[name]] = val; return; }
      if (name === 'style') { props.style = typeof val === 'string' ? styleObj(val) : val; return; }
      if (RENAME[name]) name = RENAME[name];
      if (name === 'value' && tag === 'textarea') { props.value = val == null ? '' : val; return; }
      if (name === 'checked' || name === 'open' || name === 'disabled') { props[name] = val === true || val === 'true' || val === ''; return; }
      if (typeof val === 'boolean' && name.indexOf('aria-') === 0) val = String(val);
      props[name] = val;
    });
    if ((tag === 'input' || tag === 'textarea' || tag === 'select') && 'value' in props && !props.onChange) props.readOnly = true;
    if (tag === 'input' && 'checked' in props && !props.onChange) props.readOnly = true;
    var children = tag === 'textarea' ? [] : kids(scope);
    return R.createElement.apply(null, [tag, props].concat(children.length ? [children] : []));
  }

  document.addEventListener('DOMContentLoaded', function () {
    ready.then(function () {
      var R = window.React;
      var xdc = document.querySelector('x-dc');
      var helmet = xdc.querySelector('helmet');
      if (helmet) Array.prototype.slice.call(helmet.childNodes).forEach(function (n) { document.head.appendChild(n); });
      var templ = Array.prototype.slice.call(xdc.childNodes).filter(function (n) { return !(n.nodeType === 1 && n.tagName.toLowerCase() === 'helmet'); });
      var scriptEl = document.querySelector('script[data-dc-script]');
      var meta = JSON.parse(scriptEl.getAttribute('data-props') || '{}');
      function DCLogic(props) { R.Component.call(this, props); }
      DCLogic.prototype = Object.create(R.Component.prototype);
      DCLogic.prototype.constructor = DCLogic;
      DCLogic.prototype.render = function () {
        window.__dcErrors = [];
        var vals = this.renderVals();
        return R.createElement('div', { style: { display: 'contents' } }, templ.map(function (n, i) { return conv(n, vals, i); }));
      };
      var Component = new Function('DCLogic', scriptEl.textContent + '\nreturn Component;')(DCLogic);
      var props = {};
      var q = new URLSearchParams(location.search);
      Object.keys(meta).forEach(function (k) { if (k !== '$preview' && q.has(k)) props[k] = q.get(k); });
      var host = document.createElement('div');
      xdc.replaceWith(host);
      window.ReactDOM.createRoot(host).render(R.createElement(Component, props));
    });
  });
})();
