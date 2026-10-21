/*
  Прототип «анкета на сайте → кабинет волонтёра → онбординг → встреча с координатором».
  Без сервера: состояние хранится в localStorage этого браузера.
  Тексты — в content/*.js, здесь только логика и разметка.
*/
(function () {
  "use strict";

  const FORM = window.FORM, ONB = window.ONBOARDING, DEMO = window.DEMO_CANDIDATES || [];
  const KEY = "dm-proto-v1";
  const app = document.getElementById("app");

  // ---------- состояние ----------
  const blank = () => ({ draft: {}, formStep: 0, editing: false, me: null, done: {}, test: { best: null, attempts: 0 }, run: null, meeting: null, big: false, sent: {} });
  let S = load();
  function load() {
    try { return Object.assign(blank(), JSON.parse(localStorage.getItem(KEY)) || {}); } catch (e) { return blank(); }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* приватный режим: работаем в памяти */ } }

  // ---------- утилиты ----------
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const paras = t => String(t).split(/\n\s*\n/).map(p => `<p>${esc(p)}</p>`).join("");
  const arr = v => Array.isArray(v) ? v : (v ? [v] : []);
  const first = name => String(name || "").trim().split(/\s+/)[0] || "";
  const modulesDone = () => ONB.modules.filter(m => S.done[m.id]).length;
  const allModulesDone = () => modulesDone() === ONB.modules.length;
  const testPassed = () => S.test.best != null && S.test.best >= ONB.test.pass;
  const fmtDate = iso => { try { return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }); } catch (e) { return ""; } };
  const age = d => { const b = new Date(d); if (isNaN(b)) return null; const n = new Date(); let a = n.getFullYear() - b.getFullYear(); if (n < new Date(n.getFullYear(), b.getMonth(), b.getDate())) a--; return a; };
  function toast(msg) {
    const t = document.createElement("div"); t.className = "toast"; t.textContent = msg;
    document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
  }
  function go(hash) { if (location.hash === hash) render(); else location.hash = hash; }

  // ---------- маски ввода ----------
  const cap = w => w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w;
  const MASK = {
    // пока печатают: только заглавная первая буква; при выходе из поля — полная нормализация
    name: v => v.replace(/[^A-Za-zА-Яа-яЁё\- ']/g, "").replace(/\s+/g, " ").replace(/^[\s-]+/, "").replace(/(^|[\s-])([a-zа-яё])/g, (m, a, b) => a + b.toUpperCase()),
    phone: v => {
      let d = v.replace(/\D/g, "");
      if (d[0] === "8") d = "7" + d.slice(1);
      if (d[0] !== "7") d = "7" + d;
      if (d.length > 11 && d[1] === "8") d = d[0] + d.slice(2); // набрали 8… после подставленного +7
      const p = d.slice(1, 11);
      let out = "+7";
      if (p.length) out += " (" + p.slice(0, 3);
      if (p.length > 3) out += ") " + p.slice(3, 6);
      if (p.length > 6) out += "-" + p.slice(6, 8);
      if (p.length > 8) out += "-" + p.slice(8, 10);
      return out;
    },
    telegram: v => "@" + v.trim().replace(/^@+/, "").replace(/^(https?:\/\/)?(www\.)?(t\.me|telegram\.me)\//i, "").replace(/[^A-Za-z0-9_]/g, "").slice(0, 32)
  };
  const FINAL = {
    name: v => MASK.name(v).trim().replace(/-+$/, "").split(/([\s-])/).map(w => /[\s-]/.test(w) ? w : cap(w)).join(""),
    phone: v => MASK.phone(v),
    telegram: v => v === "@" ? "" : MASK.telegram(v)
  };
  const shortHint = (f, v) => {
    if (f.mask !== "name" || f.id !== "firstName") return "";
    const full = (FORM.shortNames || {})[cap(String(v || "").trim())];
    return full ? `Это полное имя? Например, ${full}. Так координатору будет проще найти вас в документах.` : "";
  };
  const roleGroups = roles => {
    const f = FORM.steps.flatMap(s => s.fields).find(x => x.type === "roles");
    return f ? f.groups.filter(g => g.roles.some(r => arr(roles).includes(r))).map(g => g.title) : [];
  };
  const fullName = c => c.name || [c.firstName, c.lastName].filter(Boolean).join(" ");
  const openGroups = new Set();

  // ---------- шапка ----------
  function chrome(active, ribbon) {
    const tab = (h, l, k) => `<a href="${h}" class="${active === k ? "on" : ""}">${l}</a>`;
    return `
      <header class="top"><div class="wrap wide">
        <a class="brand" href="#/"><i></i>Дети Марии · волонтёры</a>
        <nav class="tabs" aria-label="Роли прототипа">
          ${tab("#/apply", "Анкета на сайте", "site")}
          ${tab("#/home", "Кабинет волонтёра", "vol")}
          ${tab("#/coord", "Координатор", "coord")}
        </nav>
        <div class="tools">
          <button class="ghost" data-act="big" aria-pressed="${S.big}">Крупный текст</button>
          <button class="ghost" data-act="reset">Сбросить демо</button>
        </div>
      </div></header>
      ${ribbon ? `<div class="ribbon ${active === "site" ? "site" : ""}">${ribbon}</div>` : ""}`;
  }

  // ---------- анкета ----------
  function visible(f, data) {
    if (!f.showIf) return true;
    const v = arr(data[f.showIf.field]), want = arr(f.showIf.value);
    return want.some(w => v.includes(w));
  }

  function fieldHtml(f, data, err) {
    const v = data[f.id];
    const label = `${esc(f.label)}${f.required ? ' <span class="req">*</span>' : ""}${f.optional ? ' <span class="opt">по желанию</span>' : ""}`;
    const name = `f-${f.id}`;
    let input = "";
    switch (f.type) {
      case "text": case "email": case "tel": case "date":
        input = `<input id="${name}" type="${f.type}" data-f="${f.id}" value="${esc(v || "")}" ${f.placeholder ? `placeholder="${esc(f.placeholder)}"` : ""} ${f.mask ? `data-mask="${f.mask}"` : ""} ${f.mask === "phone" ? 'inputmode="tel"' : ""} autocomplete="${f.autocomplete || "off"}">`;
        break;
      case "textarea":
        input = `<textarea id="${name}" data-f="${f.id}">${esc(v || "")}</textarea>`;
        break;
      case "select":
        input = `<select id="${name}" data-f="${f.id}"><option value="">Выберите…</option>${f.options.map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
        break;
      case "radio": case "checkbox":
        input = `<div class="opts" role="${f.type === "radio" ? "radiogroup" : "group"}">${f.options.map(o => {
          const on = f.type === "radio" ? v === o : arr(v).includes(o);
          return `<label class="opt-line"><input type="${f.type}" name="${name}" data-f="${f.id}" value="${esc(o)}" ${on ? "checked" : ""}><span>${esc(o)}</span></label>`;
        }).join("")}</div>`;
        break;
      case "chips":
        input = `<div class="chips">${f.options.map(o => `<button type="button" class="chip" data-chip="${f.id}" data-v="${esc(o)}" aria-pressed="${arr(v).includes(o)}">${esc(o)}</button>`).join("")}</div>
          ${f.allowOther ? `<input type="text" data-f="${f.id}Other" value="${esc(data[f.id + "Other"] || "")}" placeholder="Другое — через запятую">` : ""}`;
        break;
      case "grid":
        input = `<div class="grid-pick"><span></span>${f.cols.map(c => `<span class="h">${esc(c)}</span>`).join("")}
          ${f.rows.map(r => `<span class="rh">${esc(r)}</span>${f.cols.map(c => {
            const k = `${r}·${c}`;
            return `<button type="button" class="chip" data-chip="${f.id}" data-v="${esc(k)}" aria-pressed="${arr(v).includes(k)}" aria-label="${esc(r + ", " + c)}">✓</button>`;
          }).join("")}`).join("")}</div>`;
        break;
      case "roles": {
        const sel = arr(v);
        input = `<div class="roles">${f.groups.map((g, gi) => {
          const n = g.roles.filter(r => sel.includes(r)).length, key = f.id + gi, open = n > 0 || openGroups.has(key);
          return `<div class="rgroup ${open ? "open" : ""}">
            <button type="button" class="rhead" data-rgroup="${key}" aria-expanded="${open}"><span><b>${esc(g.title)}</b>${g.hint ? `<small>${esc(g.hint)}</small>` : ""}</span><span class="badge ${n ? "hot" : ""}">${n ? `выбрано: ${n}` : open ? "свернуть" : "открыть"}</span></button>
            ${open ? `<div class="chips">${g.roles.map(r => `<button type="button" class="chip" data-chip="${f.id}" data-v="${esc(r)}" data-redraw aria-pressed="${sel.includes(r)}">${esc(r)}</button>`).join("")}</div>` : ""}
          </div>`;
        }).join("")}
        ${f.unsure ? `<label class="opt-line"><input type="checkbox" data-f="${f.id}" value="${esc(f.unsure)}" ${sel.includes(f.unsure) ? "checked" : ""}><span>${esc(f.unsure)}</span></label>` : ""}</div>`;
        break;
      }
      case "consent":
        return `<div class="field ${err ? "bad" : ""}"><label class="opt-line"><input type="checkbox" data-f="${f.id}" data-consent ${v ? "checked" : ""}><span>${label}</span></label>${err ? `<p class="err">${esc(err)}</p>` : ""}</div>`;
    }
    const isGroup = ["radio", "checkbox", "chips", "grid", "roles"].includes(f.type);
    const hint = shortHint(f, v);
    return `<div class="field ${err ? "bad" : ""} ${f.half ? "half" : ""}">
      ${isGroup ? `<span class="lbl">${label}</span>` : `<label for="${name}">${label}</label>`}
      ${f.why ? `<p class="why">${esc(f.why)}</p>` : ""}
      ${input}
      ${f.mask === "name" ? `<p class="warn" data-warn="${f.id}" ${hint ? "" : "hidden"}>${esc(hint)}</p>` : ""}
      ${err ? `<p class="err">${esc(err)}</p>` : ""}
    </div>`;
  }

  function validate(fields, data) {
    const errs = {};
    fields.filter(f => visible(f, data)).forEach(f => {
      const v = data[f.id];
      const empty = v == null || v === "" || v === false || (Array.isArray(v) && v.length === 0);
      if (f.required && empty) errs[f.id] = f.type === "consent" ? "Без согласия мы не сможем обработать заявку" : f.type === "roles" ? "Выберите хотя бы одну роль или «Пока не знаю»" : "Заполните, пожалуйста";
      else if (!empty && f.type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) errs[f.id] = "Проверьте адрес почты";
      else if (!empty && f.mask === "phone" && String(v).replace(/\D/g, "").length !== 11) errs[f.id] = "Номер должен быть из 10 цифр после +7";
      else if (!empty && f.mask === "telegram" && v !== "@" && !/^@[A-Za-z0-9_]{5,32}$/.test(v)) errs[f.id] = "Ник — от 5 символов: латиница, цифры и _";
      else if (!empty && f.mask === "name" && !/^[А-ЯЁA-Z][а-яёa-z']+([\s-][А-ЯЁA-Z][а-яёa-z']+)*$/.test(v)) errs[f.id] = "Проверьте написание: только буквы, без сокращений";
      else if (!empty && f.id === "birthdate") { const a = age(v); if (a == null || a < 16) errs[f.id] = "Волонтёром можно стать с 16 лет"; else if (a > 110) errs[f.id] = "Проверьте дату"; }
    });
    return errs;
  }

  let formErrs = {};
  function viewApply() {
    const step = FORM.steps[S.formStep];
    const last = S.formStep === FORM.steps.length - 1;
    if (S.editing) return chrome("vol", "Платформа волонтёров · изменение ответов анкеты") + formBody(step, last);
    return chrome("site", "Так анкета выглядит на сайте фонда. После отправки человек получает ссылку в кабинет на платформе.") + formBody(step, last);
  }

  function formBody(step, last) {
    return `
      <main><div class="wrap">
        <p class="eyebrow">${S.editing ? "Профиль" : "Стать волонтёром"}</p>
        <h1>${S.editing ? "Изменить ответы" : esc(FORM.title)}</h1>
        <p class="muted" style="margin-top:10px;max-width:60ch">${esc(FORM.intro)}</p>
        <div class="form-steps">${FORM.steps.map((s, i) => `<span class="${i === S.formStep ? "on" : i < S.formStep ? "done" : ""}">${i + 1}. ${esc(s.title)}</span>`).join("")}</div>
        <div class="progress form-bar" aria-label="Шаг ${S.formStep + 1} из ${FORM.steps.length}"><i style="width:${100 * (S.formStep + 1) / FORM.steps.length}%"></i></div>
        <form class="card" id="form" novalidate>
          ${step.fields.filter(f => visible(f, S.draft)).map(f => fieldHtml(f, S.draft, formErrs[f.id])).join("")}
        </form>
        <div class="form-nav">
          ${S.formStep > 0 ? `<button class="btn sec" data-act="prev">← Назад</button>` : "<span></span>"}
          <button class="btn" data-act="${last ? "submit" : "next"}">${last ? (S.editing ? "Сохранить" : "Отправить заявку") : "Далее →"}</button>
        </div>
        ${S.editing ? `<p style="margin-top:14px"><button class="ghost" data-act="cancelEdit">Отменить изменения</button></p>` : S.me ? `<p class="muted" style="margin-top:18px;font-size:.85rem">Заявка от ${esc(fullName(S.me))} уже отправлена. Новая анкета заменит её в демо.</p>` : ""}
      </div></main>`;
  }

  function bindForm() {
    const form = document.getElementById("form");
    if (!form) return;
    const tgt = () => form.dataset.target === "me" ? S.me : S.draft;
    const rerender = () => { formErrs = {}; render(); };
    form.addEventListener("input", e => {
      const el = e.target, id = el.dataset.f;
      if (!id || el.type === "radio" || el.type === "checkbox") return;
      if (el.dataset.mask) {
        const nv = MASK[el.dataset.mask](el.value);
        if (nv !== el.value) el.value = nv;
        const w = form.querySelector(`[data-warn="${id}"]`);
        if (w) { const f = FORM.steps.flatMap(s => s.fields).find(x => x.id === id); const h = shortHint(f, nv); w.textContent = h; w.hidden = !h; }
      }
      tgt()[id] = el.value; save();
    });
    form.addEventListener("focusin", e => {
      const el = e.target;
      if (el.dataset.mask === "phone" && !el.value) el.value = "+7 (";
      if (el.dataset.mask === "telegram" && !el.value) el.value = "@";
    });
    form.addEventListener("focusout", e => {
      const el = e.target, id = el.dataset.f;
      if (!el.dataset.mask || !id) return;
      el.value = el.dataset.mask === "phone" && el.value.replace(/\D/g, "").length <= 1 ? "" : FINAL[el.dataset.mask](el.value);
      tgt()[id] = el.value; save();
    });
    form.addEventListener("change", e => {
      const el = e.target, id = el.dataset.f;
      if (!id) return;
      const T = tgt();
      if (el.hasAttribute("data-consent")) T[id] = el.checked;
      else if (el.type === "radio") T[id] = el.value;
      else if (el.type === "checkbox") {
        const set = new Set(arr(T[id]));
        el.checked ? set.add(el.value) : set.delete(el.value);
        T[id] = [...set];
      } else if (el.tagName === "SELECT") T[id] = el.value;
      else return;
      save();
      if (el.type === "radio" || el.type === "checkbox" || el.tagName === "SELECT") rerender();
    });
    form.addEventListener("click", e => {
      const g = e.target.closest("[data-rgroup]");
      if (g) { const k = g.dataset.rgroup; openGroups.has(k) ? openGroups.delete(k) : openGroups.add(k); rerender(); return; }
      const b = e.target.closest("[data-chip]");
      if (!b) return;
      const id = b.dataset.chip, T = tgt(), set = new Set(arr(T[id]));
      set.has(b.dataset.v) ? set.delete(b.dataset.v) : set.add(b.dataset.v);
      T[id] = [...set]; save();
      b.setAttribute("aria-pressed", set.has(b.dataset.v));
      if (b.hasAttribute("data-redraw")) rerender();
    });
  }

  function stepCheck() {
    const step = FORM.steps[S.formStep];
    formErrs = validate(step.fields, S.draft);
    if (Object.keys(formErrs).length) {
      render();
      const bad = document.querySelector(".field.bad");
      if (bad) bad.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    return true;
  }

  function viewSent() {
    if (!S.me) return viewApply();
    return chrome("site", "Сайт фонда · письмо волонтёру") + `
      <main><div class="wrap stack">
        <div class="card stack">
          <p class="eyebrow">Заявка №${String(S.me.submittedAt).replace(/\D/g, "").slice(-5)}</p>
          <h1>${esc(FORM.done.title)}</h1>
          <p class="muted" style="max-width:60ch">${esc(FORM.done.text)}</p>
        </div>
        <div class="card stack" style="border-style:dashed">
          <p class="eyebrow">Письмо на ${esc(S.me.email)}</p>
          <h3>${esc(first(fullName(S.me)))}, добро пожаловать в «Дети Марии»!</h3>
          <p>Мы получили вашу анкету. Следующий шаг — короткое знакомство с фондом в личном кабинете, около 25 минут. После него вы сможете выбрать время встречи с координатором.</p>
          <div><a class="btn" href="#/home">Открыть личный кабинет →</a></div>
        </div>
      </div></main>`;
  }

  // ---------- кабинет ----------
  function stages() {
    const n = modulesDone(), total = ONB.modules.length;
    return [
      { t: "Заявка", s: S.me ? "отправлена " + fmtDate(S.me.submittedAt) : "не отправлена", done: !!S.me },
      { t: "Знакомство с фондом", s: `${n} из ${total} шагов`, done: n === total },
      { t: "Тест", s: S.test.best == null ? "не пройден" : `${S.test.best} из ${ONB.test.questions.length}${testPassed() ? " — пройден" : ""}`, done: testPassed() },
      { t: "Встреча с координатором", s: S.meeting ? `${S.meeting.day}, ${S.meeting.time}` : "после теста", done: !!S.meeting },
      { t: "Первое занятие", s: "подберём на встрече", done: false }
    ];
  }

  function nextAction() {
    if (!S.me) return { e: "Сначала", t: "Заполните анкету волонтёра", h: "#/apply", b: "К анкете" };
    const m = ONB.modules.find(x => !S.done[x.id]);
    if (m) return { e: modulesDone() ? "Продолжите" : "Начните здесь", t: m.title, h: `#/learn/${m.id}`, b: modulesDone() ? "Продолжить" : "Начать" };
    if (!testPassed()) return { e: "Осталось немного", t: ONB.test.title, h: "#/test", b: "Пройти тест" };
    if (!S.meeting) return { e: "Онбординг пройден", t: "Выберите время встречи с координатором", h: "#/meet", b: "Выбрать время" };
    return { e: "Вы записаны", t: `Встреча ${S.meeting.day} в ${S.meeting.time}`, h: "#/meet", b: "Подробнее" };
  }

  function viewHome() {
    if (!S.me) return chrome("vol", "Кабинет волонтёра на платформе") + `<main><div class="wrap stack"><div class="card stack"><h2>Кабинет появится после анкеты</h2><p class="muted">В прототипе сначала заполните анкету на «сайте фонда» — её ответы попадут сюда и к координатору.</p><div class="row"><a class="btn" href="#/apply">Заполнить анкету</a><button class="btn sec" data-act="quick">Заполнить демо-ответами</button></div></div></div></main>`;
    const st = stages(), nowI = st.findIndex(s => !s.done), na = nextAction();
    return chrome("vol", "Платформа волонтёров · личный кабинет") + `
      <main><div class="wrap stack" style="gap:28px">
        <div class="stack" style="gap:8px">
          <p class="eyebrow">Личный кабинет</p>
          <h1>Здравствуйте, ${esc(first(fullName(S.me)))}!</h1>
          <p class="muted">${esc(ONB.intro)}</p>
        </div>
        <ol class="path">${st.map((s, i) => `<li class="${s.done ? "done" : i === nowI ? "now" : ""}"><span class="n">${s.done ? "✓" : i + 1}</span><b>${esc(s.t)}</b><small>${esc(s.s)}</small></li>`).join("")}</ol>
        <div class="next"><div><p class="eyebrow">${esc(na.e)}</p><h2 style="margin-top:6px">${esc(na.t)}</h2></div><a class="btn" href="${na.h}">${esc(na.b)} →</a></div>
        <section class="stack" style="gap:10px">
          <div class="row" style="justify-content:space-between"><h2>${esc(ONB.title)}</h2><span class="muted">${modulesDone()} из ${ONB.modules.length}</span></div>
          <div class="progress"><i style="width:${100 * modulesDone() / ONB.modules.length}%"></i></div>
          <div class="mods">
            ${ONB.modules.map((m, i) => `<a class="mod ${S.done[m.id] ? "done" : ""}" href="#/learn/${m.id}">
              <span class="num">${S.done[m.id] ? "✓" : i + 1}</span>
              <span class="stack" style="gap:2px"><h3>${esc(m.title)}</h3><span class="meta">${m.minutes} мин${m.draft ? ' <span class="badge draft">Черновик</span>' : ""}</span></span>
              <span class="muted">→</span></a>`).join("")}
            <a class="mod ${testPassed() ? "done" : ""} ${allModulesDone() ? "" : "locked"}" href="#/test">
              <span class="num">${testPassed() ? "✓" : ONB.modules.length + 1}</span>
              <span class="stack" style="gap:2px"><h3>${esc(ONB.test.title)}</h3><span class="meta">${ONB.test.questions.length} вопросов${allModulesDone() ? "" : " · откроется после всех шагов"}</span></span>
              <span class="muted">→</span></a>
          </div>
        </section>
        <section class="card stack" style="gap:10px">
          <div class="row" style="justify-content:space-between"><h3>Ваш профиль</h3><a href="#/profile" class="btn sec small">Открыть</a></div>
          <p class="muted">${esc(arr(S.me.roles).join(" · ") || "Роли не выбраны")}</p>
          <p class="muted" style="font-size:.85rem">После встречи с координатором здесь появятся занятия и мероприятия, подобранные под ваши навыки и время.</p>
        </section>
      </div></main>`;
  }

  // ---------- модуль ----------
  function blockHtml(b) {
    switch (b.type) {
      case "lead": return `<p class="lead">${esc(b.text)}</p>`;
      case "text": return `<div class="text">${paras(b.text)}</div>`;
      case "facts": return `<div class="facts">${b.items.map(([n, l]) => `<div><b>${esc(n)}</b><span>${esc(l)}</span></div>`).join("")}</div>`;
      case "timeline": return `<div class="timeline">${b.items.map(([y, t, d]) => `<div><span class="y">${esc(y)}</span><h3>${esc(t)}</h3><p class="muted">${esc(d)}</p></div>`).join("")}</div>`;
      case "cards": return b.open
        ? `<div class="cards">${b.items.map(([t, d]) => `<div><h3>${esc(t)}</h3><p class="muted">${esc(d)}</p></div>`).join("")}</div>`
        : `<div><p class="muted" style="margin-bottom:10px;font-size:.9rem">Нажмите на карточку, чтобы прочитать</p><div class="cards">${b.items.map(([t, d], i) => `<button aria-expanded="false" data-card><span class="eyebrow">${String(i + 1).padStart(2, "0")}</span><h3>${esc(t)}</h3><p class="muted" hidden>${esc(d)}</p><span class="more">Подробнее</span></button>`).join("")}</div></div>`;
      case "list": return `<div class="list">${b.title ? `<h3>${esc(b.title)}</h3>` : ""}<ul>${b.items.map(i => `<li>${esc(i)}</li>`).join("")}</ul></div>`;
      case "steps": return `<div class="steps">${b.items.map(([t, d]) => `<div><h3>${esc(t)}</h3><p class="muted">${esc(d)}</p></div>`).join("")}</div>`;
      case "phrases": return `<div class="stack" style="gap:8px"><h3>Как говорить</h3><div class="phrase-head"><span>Лучше так</span><span>Не так</span></div><div class="phrases">${b.items.map(([s, a, w]) => `<div><span class="say">${esc(s)}</span><span class="avoid">${esc(a)}</span><span class="why">${esc(w)}</span></div>`).join("")}</div></div>`;
      case "situations": return `<div class="stack" style="gap:8px"><h3>Если случилось…</h3>${b.items.map(s => `<details class="sit"><summary>${esc(s.title)}</summary><div class="body"><div class="do"><b>Что делать</b><ul>${s.do.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div><div class="dont"><b>Чего не делать</b><ul>${s.dont.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div></details>`).join("")}</div>`;
      case "callout": return `<div class="callout ${b.tone === "warn" ? "warn" : ""}">${esc(b.text)}</div>`;
      case "pillars": return `<div class="pillars">${b.items.map(x => `<div class="pillar"><h3>${esc(x.title)}</h3><p class="muted">${esc(x.text)}</p><p class="eyebrow">На занятии это значит</p><ul>${x.items.map(i => `<li>${esc(i)}</li>`).join("")}</ul><p class="from">Из кодекса: ${esc(x.from)}</p></div>`).join("")}</div>`;
      case "check": return `<div class="stack" style="gap:8px"><h3>${esc(b.title)}</h3>${b.intro ? `<p class="muted">${esc(b.intro)}</p>` : ""}${b.items.map(x => `<details class="sit check"><summary>${esc(x.q)}</summary><div class="ans"><p>${esc(x.a)}</p><p class="from">${esc(x.p)}</p></div></details>`).join("")}</div>`;
      case "more": return `<details class="more-block"><summary>${esc(b.title)}</summary><div class="blocks">${b.blocks.map(blockHtml).join("")}</div></details>`;
      case "video": return videoHtml(b);
      default: return "";
    }
  }

  function videoHtml(b) {
    const head = `<div class="vmeta"><b>${esc(b.title)}</b>${b.duration ? `<span class="muted">${esc(b.duration)}</span>` : ""}</div>`;
    if (!b.src) return `<figure class="video"><div class="vbox empty"><span class="play">▶</span><span>Видео появится здесь</span></div>${head}${b.note ? `<figcaption class="draft-note">${esc(b.note)}</figcaption>` : ""}</figure>`;
    let src = b.src, m;
    if ((m = src.match(/(?:youtu\.be\/|v=)([\w-]{11})/))) src = `https://www.youtube.com/embed/${m[1]}`;
    else if ((m = src.match(/rutube\.ru\/video\/([\w]+)/))) src = `https://rutube.ru/play/embed/${m[1]}`;
    else if ((m = src.match(/vk(?:video)?\.(?:com|ru)\/video(-?\d+)_(\d+)/))) src = `https://vk.com/video_ext.php?oid=${m[1]}&id=${m[2]}&hd=2`;
    const player = /\.(mp4|webm)(\?|$)/i.test(src)
      ? `<video class="vbox" src="${esc(src)}" controls preload="metadata"></video>`
      : `<iframe class="vbox" src="${esc(src)}" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowfullscreen loading="lazy" title="${esc(b.title)}"></iframe>`;
    return `<figure class="video">${player}${head}</figure>`;
  }

  function viewLearn(id) {
    if (!S.me) return viewHome();
    const i = ONB.modules.findIndex(m => m.id === id);
    if (i < 0) return viewHome();
    const m = ONB.modules[i], nxt = ONB.modules[i + 1];
    return chrome("vol", "Платформа волонтёров · знакомство с фондом") + `
      <main><div class="wrap">
        <div class="mod-head">
          <div class="row" style="justify-content:space-between">
            <a href="#/home" class="muted" style="text-decoration:none">← Кабинет</a>
            <nav class="pills" aria-label="Шаги">${ONB.modules.map((x, k) => `<a href="#/learn/${x.id}" class="${k === i ? "on" : S.done[x.id] ? "done" : ""}" title="${esc(x.title)}">${k + 1}</a>`).join("")}</nav>
          </div>
          <p class="eyebrow">Шаг ${i + 1} из ${ONB.modules.length} · ${m.minutes} мин</p>
          <h1>${esc(m.title)}</h1>
          ${m.draft ? `<p class="draft-note"><b>Черновик.</b> ${esc(m.source)}</p>` : `<p class="muted" style="font-size:.85rem">Источник: ${esc(m.source)}</p>`}
        </div>
        ${m.form ? matchingHtml() : `<div class="blocks">${m.blocks.map(blockHtml).join("")}</div>`}
        <div class="mod-foot">
          ${i > 0 ? `<a class="btn sec" href="#/learn/${ONB.modules[i - 1].id}">← Назад</a>` : "<span></span>"}
          <button class="btn" data-act="done" data-id="${m.id}">${nxt ? "Понятно, дальше →" : "Понятно, к тесту →"}</button>
        </div>
      </div></main>`;
  }

  function matchingHtml() {
    const M = FORM.matching;
    return `<p class="lead">${esc(M.intro)}</p>
      <form class="card" id="form" data-target="me" novalidate style="margin-top:20px">
        ${M.fields.filter(f => visible(f, S.me)).map(f => fieldHtml(f, S.me)).join("")}
      </form>`;
  }

  // ---------- тест ----------
  function viewTest() {
    if (!S.me) return viewHome();
    const T = ONB.test, N = T.questions.length;
    let body;
    if (!allModulesDone()) {
      body = `<div class="card stack"><h2>Тест откроется после всех шагов</h2><p class="muted">Пройдено ${modulesDone()} из ${ONB.modules.length}.</p><div><a class="btn" href="${nextAction().h}">Продолжить знакомство</a></div></div>`;
    } else if (!S.run) {
      body = `<div class="card stack"><h1>${esc(T.title)}</h1><p class="muted">${esc(T.intro)}</p>
        ${S.test.best != null ? `<p>Лучший результат: <b>${S.test.best} из ${N}</b>${testPassed() ? ' <span class="badge ok">пройден</span>' : ""}</p>` : ""}
        <div class="row"><button class="btn" data-act="start">${S.test.attempts ? "Пройти ещё раз" : "Начать тест"}</button>${testPassed() ? `<a class="btn sec" href="#/meet">К записи на встречу</a>` : ""}</div>
        <p class="muted" style="font-size:.8rem">${esc(T.source)}</p></div>`;
    } else if (S.run.i >= N) {
      const score = S.run.answers.filter((a, k) => a === T.questions[k].a).length, ok = score >= T.pass;
      const wrong = T.questions.map((q, k) => ({ q, k })).filter(x => S.run.answers[x.k] !== x.q.a);
      body = `<div class="card stack" style="text-align:center;justify-items:center">
          <p class="eyebrow">Результат</p><p class="score">${score} / ${N}</p>
          <h2>${ok ? "Отлично, тест пройден!" : "Почти получилось"}</h2>
          <p class="muted" style="max-width:50ch">${ok ? "Теперь можно выбрать время встречи с координатором." : `Нужно ${T.pass} правильных ответов. Посмотрите разбор ниже и попробуйте ещё раз.`}</p>
          <div class="row" style="justify-content:center">${ok ? `<a class="btn" href="#/meet">Выбрать время встречи →</a>` : ""}<button class="btn ${ok ? "sec" : ""}" data-act="start">Пройти ещё раз</button></div>
        </div>
        ${wrong.length ? `<section class="stack" style="gap:8px;margin-top:20px"><h3>Разбор ошибок</h3>${wrong.map(x => `<div class="card tight stack" style="gap:6px"><b>${esc(x.q.q)}</b><p>Правильно: ${esc(x.q.o[x.q.a])}</p><p class="muted">${esc(x.q.e)}</p></div>`).join("")}</section>` : ""}`;
    } else {
      const k = S.run.i, q = T.questions[k], ans = S.run.answers[k], shown = ans != null;
      body = `<div class="stack" style="gap:6px"><div class="row" style="justify-content:space-between"><p class="eyebrow">Вопрос ${k + 1} из ${N}</p><button class="ghost" data-act="quit">Выйти</button></div><div class="progress"><i style="width:${100 * k / N}%"></i></div></div>
        <div class="card" style="margin-top:14px"><h2>${esc(q.q)}</h2>
          <div class="q-opts">${q.o.map((o, j) => `<button class="q-opt ${shown && j === q.a ? "right" : ""} ${shown && j === ans && ans !== q.a ? "wrong" : ""}" data-act="answer" data-j="${j}" ${shown ? "disabled" : ""}>${esc(o)}</button>`).join("")}</div>
          ${shown ? `<div class="expl ${ans === q.a ? "right" : "wrong"}"><b>${ans === q.a ? "Верно." : "Не совсем."}</b> ${esc(q.e)}</div><div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-act="nextq">${k + 1 < N ? "Следующий вопрос →" : "Посмотреть результат"}</button></div>` : ""}
        </div>`;
    }
    return chrome("vol", "Платформа волонтёров · тест") + `<main><div class="wrap"><a href="#/home" class="muted" style="text-decoration:none">← Кабинет</a><div style="margin-top:14px">${body}</div></div></main>`;
  }

  // ---------- встреча ----------
  let pickedSlot = null;
  function viewMeet() {
    if (!S.me) return viewHome();
    const M = ONB.meeting;
    let body;
    if (!testPassed()) {
      body = `<div class="card stack"><h2>Запись откроется после теста</h2><p class="muted">Сначала пройдите знакомство с фондом и тест.</p><div><a class="btn" href="${nextAction().h}">${esc(nextAction().b)}</a></div></div>`;
    } else if (S.meeting) {
      body = `<div class="card stack"><span class="badge ok" style="justify-self:start">Вы записаны</span><h1>${esc(S.meeting.day)}, ${esc(S.meeting.time)}</h1><p>${esc(S.meeting.where)}</p>
        <p class="muted">${esc(M.coordinator)} уже видит ваши ответы из анкеты и результат теста. Напомним о встрече накануне в ${esc(arr(S.me.channels)[0] || "почте")}.</p>
        <div class="row"><button class="btn sec" data-act="unmeet">Перенести</button><a class="btn sec" href="#/home">В кабинет</a></div></div>`;
    } else {
      body = `<div class="card stack"><p class="eyebrow">Последний шаг онбординга</p><h1>${esc(M.title)}</h1><p class="muted">${esc(M.text)}</p><p>Проводит: <b>${esc(M.coordinator)}</b></p>
        <div class="slots">${M.slots.map((s, i) => `<button class="slot" data-act="slot" data-i="${i}" aria-pressed="${pickedSlot === i}"><span class="muted">${esc(s.day)}</span><b>${esc(s.time)}</b><span class="muted" style="font-size:.85rem">${esc(s.where)}</span></button>`).join("")}</div>
        <div><button class="btn" data-act="meet" ${pickedSlot == null ? "disabled" : ""}>Записаться</button></div>
        <p class="muted" style="font-size:.85rem">Ни одно время не подходит? Координатор свяжется с вами и предложит другое.</p></div>`;
    }
    return chrome("vol", "Платформа волонтёров · встреча с координатором") + `<main><div class="wrap"><a href="#/home" class="muted" style="text-decoration:none">← Кабинет</a><div style="margin-top:14px">${body}</div></div></main>`;
  }

  // ---------- профиль ----------
  function answersHtml(c) {
    return FORM.steps.concat(FORM.matching).map(s => {
      const rows = s.fields.filter(f => f.type !== "consent" && visible(f, c)).map(f => {
        let v = c[f.id];
        if (f.type === "chips" && c[f.id + "Other"]) v = arr(v).concat(c[f.id + "Other"]);
        if (f.type === "date" && v) v = `${new Date(v).toLocaleDateString("ru-RU")} (${age(v)} лет)`;
        const txt = Array.isArray(v) ? v.join(", ") : v;
        return txt ? `<dt>${esc(f.label)}</dt><dd>${esc(txt)}</dd>` : "";
      }).join("");
      return rows ? `<section class="stack" style="gap:10px"><h3>${esc(s.title)}</h3><dl class="answers">${rows}</dl></section>` : "";
    }).join("");
  }

  function viewProfile() {
    if (!S.me) return viewHome();
    return chrome("vol", "Платформа волонтёров · профиль") + `<main><div class="wrap stack" style="gap:20px">
      <a href="#/home" class="muted" style="text-decoration:none">← Кабинет</a>
      <div class="row" style="justify-content:space-between"><h1>${esc(fullName(S.me))}</h1><button class="btn sec small" data-act="edit">Изменить ответы</button></div>
      <p class="muted">Это ответы из анкеты. Их видите вы и координатор — по ним мы подбираем занятия.</p>
      <div class="card stack" style="gap:24px">${answersHtml(S.me)}</div>
    </div></main>`;
  }

  // ---------- координатор ----------
  function candidates() {
    const list = DEMO.map(c => Object.assign({}, c));
    if (S.me) list.unshift(Object.assign({}, S.me, { id: "me", you: true, progress: { modules: modulesDone(), test: S.test.best, meeting: S.meeting ? `${S.meeting.day}, ${S.meeting.time}` : null } }));
    return list;
  }
  function statusOf(c) {
    const p = c.progress, total = ONB.modules.length;
    if (p.meeting) return ["Записан на встречу", "ok", "meet"];
    if (p.test != null && p.test >= ONB.test.pass) return ["Ждёт записи", "hot", "ready"];
    if (p.modules > 0) return [`Учится ${p.modules}/${total}`, "wait", "learn"];
    return ["Новая заявка", "", "new"];
  }
  let coordFilter = "all";
  function viewCoord(id) {
    const list = candidates();
    const counts = { all: list.length, new: 0, learn: 0, ready: 0, meet: 0 };
    list.forEach(c => counts[statusOf(c)[2]]++);
    const shown = list.filter(c => coordFilter === "all" || statusOf(c)[2] === coordFilter);
    const sel = list.find(c => c.id === id);
    const f = (k, l) => `<button class="chip" data-act="filter" data-k="${k}" aria-pressed="${coordFilter === k}">${l} · ${counts[k]}</button>`;
    const flags = c => {
      const out = [];
      if (arr(c.physical).some(x => !/^Нет/.test(x))) out.push('<span class="badge">💪 физ. помощь</span>');
      if (/^Постоянно/.test(c.participation || "")) out.push('<span class="badge ok">постоянно</span>');
      if (/^Разово/.test(c.participation || "")) out.push('<span class="badge">разово</span>');
      if (age(c.birthdate) != null && age(c.birthdate) < 18) out.push('<span class="badge draft">16–17 лет</span>');
      if (arr(c.comfort).length) out.push('<span class="badge wait">помощь с дорогой</span>');
      if (c.record === "Хочу сначала обсудить") out.push('<span class="badge draft">справка?</span>');
      return out.join("");
    };
    const detail = sel ? `<aside class="card stack" style="gap:16px">
        <div class="row" style="justify-content:space-between"><h2>${esc(fullName(sel))}</h2><a href="#/coord" class="ghost" style="text-decoration:none">Закрыть</a></div>
        <div class="row"><span class="badge ${statusOf(sel)[1]}">${esc(statusOf(sel)[0])}</span>${flags(sel)}</div>
        <dl class="answers">
          <dt>Онбординг</dt><dd>${sel.progress.modules} из ${ONB.modules.length} шагов</dd>
          <dt>Тест</dt><dd>${sel.progress.test == null ? "не пройден" : `${sel.progress.test} из ${ONB.test.questions.length}`}</dd>
          <dt>Встреча</dt><dd>${esc(sel.progress.meeting || "не записан")}</dd>
          <dt>Связь</dt><dd>${esc(arr(sel.channels).join(", "))}${sel.telegram ? " · " + esc(sel.telegram) : ""}<br>${esc(sel.phone)} · ${esc(sel.email)}</dd>
        </dl>
        <div class="card tight stack" style="gap:8px;background:var(--bg)">
          <b>Написать</b>
          <div class="row">${arr(sel.channels).map(ch => `<button class="chip" data-act="send" data-id="${sel.id}" data-ch="${esc(ch)}">${esc(ch)}</button>`).join("")}</div>
          <p class="muted" style="font-size:.85rem">${statusOf(sel)[2] === "ready" ? "Шаблон: «Вы прошли знакомство с фондом — выберите время встречи»" : statusOf(sel)[2] === "learn" ? "Шаблон: «Как идёт знакомство с фондом? Можем помочь»" : "Шаблон: «Спасибо за заявку! Ссылка в кабинет»"}</p>
          ${S.sent[sel.id] ? `<p class="muted" style="font-size:.85rem">Отправлено: ${esc(S.sent[sel.id].join(", "))}</p>` : ""}
        </div>
        <div class="stack" style="gap:20px">${answersHtml(sel)}</div>
      </aside>` : `<aside class="card stack"><h3>Выберите кандидата</h3><p class="muted">Справа появятся ответы из анкеты, прогресс онбординга и быстрые сообщения.</p></aside>`;
    return chrome("coord", "Платформа волонтёров · рабочее место координатора") + `
      <main><div class="wrap wide stack" style="gap:18px">
        <div><p class="eyebrow">Координатор</p><h1>Новые волонтёры</h1></div>
        <div class="filters">${f("all", "Все")}${f("new", "Новые заявки")}${f("learn", "Учатся")}${f("ready", "Ждут записи")}${f("meet", "Записаны")}</div>
        <div class="cols">
          <div class="tablewrap"><table class="table">
            <thead><tr><th>Кандидат</th><th>Роли</th><th>Когда</th><th>Статус</th></tr></thead>
            <tbody>${shown.map(c => `<tr data-go="#/coord/${c.id}" ${c.id === id ? 'style="background:var(--heart-soft)"' : ""}>
              <td><b>${esc(fullName(c))}</b>${c.you ? ' <span class="badge hot you">ваша анкета</span>' : ""}<br><span class="muted" style="font-size:.8rem">${esc(c.area || "")} · ${fmtDate(c.submittedAt)}</span></td>
              <td>${esc(arr(c.roles).slice(0, 2).join(", "))}${arr(c.roles).length > 2 ? ` <span class="muted">+${arr(c.roles).length - 2}</span>` : ""}<div class="flags" style="margin-top:4px">${flags(c)}</div></td>
              <td>${esc(arr(c.slots).join(", ").replace(/·/g, " "))}</td>
              <td><span class="badge ${statusOf(c)[1]}">${esc(statusOf(c)[0])}</span></td></tr>`).join("") || `<tr><td colspan="4" class="muted">Никого в этом статусе</td></tr>`}</tbody>
          </table></div>
          ${detail}
        </div>
      </div></main>`;
  }

  // ---------- роутер ----------
  function render() {
    const parts = location.hash.replace(/^#\/?/, "").split("/");
    const route = parts[0] || (S.me ? "home" : "apply");
    document.documentElement.classList.toggle("big", !!S.big);
    const views = { apply: viewApply, sent: viewSent, home: viewHome, learn: () => viewLearn(parts[1]), test: viewTest, meet: viewMeet, profile: viewProfile, coord: () => viewCoord(parts[1]) };
    app.innerHTML = (views[route] || viewHome)();
    bindForm();
  }

  // ---------- действия ----------
  document.addEventListener("click", e => {
    const row = e.target.closest("[data-go]");
    if (row) { go(row.dataset.go); return; }
    const card = e.target.closest("[data-card]");
    if (card) {
      const open = card.getAttribute("aria-expanded") === "true";
      card.setAttribute("aria-expanded", String(!open));
      card.querySelector("p").hidden = open;
      card.querySelector(".more").textContent = open ? "Подробнее" : "Свернуть";
      return;
    }
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    if (act === "big") { S.big = !S.big; save(); render(); }
    else if (act === "reset") { S = blank(); save(); formErrs = {}; go("#/apply"); }
    else if (act === "next") { e.preventDefault(); if (stepCheck()) { S.formStep++; save(); formErrs = {}; render(); scrollTo(0, 0); } }
    else if (act === "prev") { e.preventDefault(); S.formStep--; save(); formErrs = {}; render(); scrollTo(0, 0); }
    else if (act === "submit") {
      e.preventDefault();
      if (!stepCheck()) return;
      const derived = { name: fullName(Object.assign({}, S.draft, { name: "" })), directions: roleGroups(S.draft.roles) };
      if (S.editing) {
        S.me = Object.assign({}, S.draft, derived, { submittedAt: S.me.submittedAt });
        S.draft = {}; S.formStep = 0; S.editing = false;
        save(); go("#/profile"); toast("Ответы обновлены"); return;
      }
      S.me = Object.assign({}, S.draft, derived, { submittedAt: new Date().toISOString() });
      S.draft = {}; S.formStep = 0; S.done = {}; S.test = { best: null, attempts: 0 }; S.run = null; S.meeting = null; S.sent = {};
      save(); go("#/sent"); scrollTo(0, 0);
    }
    else if (act === "quick") { S.me = Object.assign({}, DEMO[0], { id: undefined, progress: undefined, firstName: "Анна", lastName: "Соколова", name: "Анна Соколова", email: "anna@example.com", submittedAt: new Date().toISOString() }); save(); render(); }
    else if (act === "done") {
      S.done[b.dataset.id] = true; save();
      const i = ONB.modules.findIndex(m => m.id === b.dataset.id), nxt = ONB.modules[i + 1];
      go(nxt ? `#/learn/${nxt.id}` : "#/test"); scrollTo(0, 0);
    }
    else if (act === "start") { S.run = { i: 0, answers: [] }; save(); render(); }
    else if (act === "quit") { S.run = null; save(); render(); }
    else if (act === "answer") { S.run.answers[S.run.i] = +b.dataset.j; save(); render(); }
    else if (act === "nextq") {
      S.run.i++;
      if (S.run.i >= ONB.test.questions.length) {
        const score = S.run.answers.filter((a, k) => a === ONB.test.questions[k].a).length;
        S.test.attempts++; S.test.best = Math.max(S.test.best == null ? 0 : S.test.best, score);
      }
      save(); render(); scrollTo(0, 0);
    }
    else if (act === "slot") { pickedSlot = +b.dataset.i; render(); }
    else if (act === "meet") { S.meeting = ONB.meeting.slots[pickedSlot]; pickedSlot = null; save(); render(); toast("Готово! Координатор получил вашу заявку"); }
    else if (act === "unmeet") { S.meeting = null; save(); render(); }
    else if (act === "edit") { S.draft = Object.assign({}, S.me); S.formStep = 0; S.editing = true; save(); go("#/apply"); }
    else if (act === "cancelEdit") { S.draft = {}; S.formStep = 0; S.editing = false; save(); go("#/profile"); }
    else if (act === "filter") { coordFilter = b.dataset.k; render(); }
    else if (act === "send") { const id = b.dataset.id; (S.sent[id] = S.sent[id] || []).push(b.dataset.ch); save(); render(); toast(`Сообщение отправлено в ${b.dataset.ch} (демо)`); }
  });

  addEventListener("hashchange", () => { formErrs = {}; render(); });
  render();
})();
