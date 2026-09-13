// Фронтенд SMTP MAILER. Общается с Python-бэкендом через мост pywebview:
// window.pywebview.api.<метод>() возвращает Promise с JSON-результатом.
//
// ОПТИМИЗАЦИЯ БОЛЬШИХ ОБЪЁМОВ: фронт НИКОГДА не тащит весь массив данных. Мост
// отдаёт только текущую СТРАНИЦУ (page_content/page_recipients/page_proxies/
// page_smtp), поэтому и передача, и DOM остаются лёгкими хоть на 10, хоть на
// миллионе строк. Полные данные лежат в менеджерах бэкенда — рассылка и проверки
// идут по всему объёму.

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const api = () => window.pywebview.api;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function setMsg(id, text, cls) {
  const el = $("#" + id); if (!el) return;
  el.textContent = text || ""; el.className = "msg" + (cls ? " " + cls : "");
}

// ── Переключение вкладок ────────────────────────────────────────────────
let activeTab = "setup";
let _busy = false;  // true во время проверки прокси/SMTP — весь UI заблокирован (только просмотр)
$("#tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab"); if (!btn) return;
  activeTab = btn.dataset.tab;
  $$(".tab").forEach((t) => t.classList.toggle("active", t === btn));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === activeTab));
  onTabEnter(activeTab);
});

function onTabEnter(tab) {
  if (tab === "setup") { pagers.proxies.reload(); pagers.smtp.reload(); }
  else if (tab === "content") { ["subjects", "bodies", "senders", "links"].forEach((k) => pagers[k].reload()); }
  else if (tab === "campaign") { pagers.recipients.reload(); saveCampaignCfg(); }
  else if (tab === "plan") refreshPlan();
  else if (tab === "send") { refreshResumeBanner(); tick(); }
  else if (tab === "stats") tick();
}

// ── Бейджи вкладок ──────────────────────────────────────────────────────
function refreshBadges() {
  api().status().then((s) => {
    $("#tb-setup").textContent = s.smtp.alive;
    $("#tb-content").textContent = s.bodies;
    $("#tb-campaign").textContent = s.recipients;
  });
}

// ── Пагинатор: общий механизм для всех больших списков ──────────────────
// Держит offset/limit/total, дёргает fetch(offset,limit) у моста и рисует одну
// страницу. Футер (‹ N–M из TOTAL ›) показывается только когда есть что листать.
function makePager(opts) {
  const foot = $("#" + opts.footId);
  const state = { offset: 0, limit: 200, total: 0 };
  function updateFoot() {
    if (!foot) return;
    const from = state.total ? state.offset + 1 : 0;
    const to = Math.min(state.offset + state.limit, state.total);
    foot.querySelector(".pg-label").textContent = `${from}–${to} из ${state.total}`;
    // _busy держит стрелки заблокированными во время проверки (иначе refresh их вернул бы).
    foot.querySelector(".pg-prev").disabled = _busy || state.offset <= 0;
    foot.querySelector(".pg-next").disabled = _busy || state.offset + state.limit >= state.total;
    foot.hidden = state.total <= state.limit;  // всё влезло на одну страницу — футер не нужен
  }
  function apply(r) {
    state.total = r.total || 0;
    state.offset = r.offset || 0;
    if (r.limit) state.limit = r.limit;
    opts.render(r); updateFoot(); return r;
  }
  function go(off) { return opts.fetch(off, state.limit).then(apply); }
  if (foot) {
    foot.querySelector(".pg-prev").onclick = () => go(Math.max(0, state.offset - state.limit));
    foot.querySelector(".pg-next").onclick = () => go(state.offset + state.limit);
  }
  return { reload: () => go(0), refresh: () => go(state.offset), state };
}

// рендер страниц контента (тексты в <pre>)
function renderContent(kind, r) {
  const pre = $("#" + kind + "-preview");
  if (kind === "links") {
    pre.textContent = (r.legend ? r.legend + "\n\n" : "") + (r.text || "(пусто)");
  } else {
    pre.textContent = r.text || "(пусто)";
  }
}
// рендер страницы получателей (строки таблицы)
function renderRecipients(r) {
  $("#recipients-count").textContent = r.total || 0;
  const body = $("#recipients-body"); body.innerHTML = "";
  if (!r.total) {
    body.innerHTML = `<tr><td colspan="2" style="color:var(--dim2);text-align:center;padding:26px">База не загружена</td></tr>`;
    return;
  }
  (r.rows || []).forEach((rc) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(rc.email)}</td><td>${esc(rc.name || "—")}</td>`;
    body.appendChild(tr);
  });
}

const pagers = {
  subjects: makePager({ footId: "subjects-pager", fetch: (o, l) => api().page_content("subjects", o, l), render: (r) => renderContent("subjects", r) }),
  bodies: makePager({ footId: "bodies-pager", fetch: (o, l) => api().page_content("bodies", o, l), render: (r) => renderContent("bodies", r) }),
  senders: makePager({ footId: "senders-pager", fetch: (o, l) => api().page_content("senders", o, l), render: (r) => renderContent("senders", r) }),
  links: makePager({ footId: "links-pager", fetch: (o, l) => api().page_content("links", o, l), render: (r) => renderContent("links", r) }),
  recipients: makePager({ footId: "recipients-pager", fetch: (o, l) => api().page_recipients(o, l), render: renderRecipients }),
  proxies: makePager({ footId: "px-pager", fetch: (o, l) => api().page_proxies(o, l), render: (r) => renderList("proxies", r) }),
  smtp: makePager({ footId: "sm-pager", fetch: (o, l) => api().page_smtp(o, l), render: (r) => renderList("smtp", r) }),
};

// ── Загрузка/очистка через диалог ───────────────────────────────────────
$$("[data-load]").forEach((btn) => btn.addEventListener("click", () => {
  const kind = btn.dataset.load;
  btn.disabled = true;
  api().pick_and_load(kind).then((r) => handleLoad(kind, r)).finally(() => (btn.disabled = false));
}));
$$("[data-clear]").forEach((btn) => btn.addEventListener("click", () => {
  const kind = btn.dataset.clear;
  api()["clear_" + kind]().then((r) => handleLoad(kind, r));
}));

function handleLoad(kind, r) {
  if (!r || r.cancelled) return;
  if (r.error) {
    if (kind === "recipients") setMsg("recipients-msg", "✗ " + r.error, "err");
    else console.error(kind, r.error);
    return;
  }
  // Обновляем счётчик в заголовке блока (сами данные придут постранично).
  if (kind === "subjects" || kind === "bodies" || kind === "senders") $("#" + kind + "-count").textContent = r.total || 0;
  else if (kind === "links") $("#links-count").textContent = (r.files ? r.files.length : 0);
  else if (kind === "recipients") $("#recipients-count").textContent = r.total || 0;
  if (pagers[kind]) pagers[kind].reload();  // показать первую страницу
  refreshBadges();
}

// ── Прокси / SMTP: рендер страницы (счётчики + окно элементов) ──────────
function renderList(kind, r) {
  const p = kind === "proxies" ? "px" : "sm";
  $("#" + p + "-total").textContent = r.total || 0;
  $("#" + p + "-alive").textContent = r.alive || 0;
  $("#" + p + "-dead").textContent = r.dead || 0;
  const untested = (r.total || 0) - (r.alive || 0) - (r.dead || 0);
  $("#" + p + "-untested").textContent = untested < 0 ? 0 : untested;
  setSetupButtons(kind, r);
  const list = $("#" + p + "-list");
  const items = r.items || [];
  if (!items.length) {
    list.innerHTML = `<div class="empty">${kind === "proxies" ? "Прокси не загружены" : "SMTP-аккаунты не загружены"}</div>`;
    return;
  }
  list.innerHTML = items.map((it) => kind === "proxies" ? proxyRow(it) : smtpRow(it)).join("");
}
// Доступность кнопок тулбара «Настроек» по состоянию пула:
//  • «Проверить все» и «Очистить» — активны, только когда что-то загружено и не идёт проверка;
//  • «Убрать мёртвые» — активна только когда ВСЁ проверено (нет непроверенных), не идёт
//    проверка и есть кого убирать (мёртвые > 0).
function setSetupButtons(kind, r) {
  const p = kind === "proxies" ? "px" : "sm";
  const total = r.total || 0, alive = r.alive || 0, dead = r.dead || 0, running = !!r.running;
  const loaded = total > 0;
  const busyk = running || _busy;  // во время ЛЮБОЙ проверки всё заблокировано
  $("#" + p + "-check").disabled = !loaded || busyk;
  $("#" + p + "-clear").disabled = !loaded || busyk;
  // «Убрать мёртвые» активна, когда ЕСТЬ мёртвые и не идёт проверка. Непроверенные «?»
  // (обычно проверку сорвал прокси/сеть — это не значит, что аккаунт мёртв) удаление
  // НЕ блокируют: иначе с флаки-прокси «Не пров.» никогда не станет 0 и удалить мёртвые
  // было бы нельзя. Мёртвые появляются только после проверки, так что до неё dead=0 и
  // кнопка сама неактивна.
  const rd = $("#" + p + "-remove-dead");
  rd.disabled = !(loaded && !busyk && dead > 0);
  rd.title = dead > 0
    ? `Удалить ${dead} мёртвых (непроверенные «?» не трогаем — их можно перепроверить)`
    : "Мёртвых аккаунтов нет — удалять нечего";
}
const STLABEL = { alive: "Живой", dead: "Мёртвый", untested: "?", checking: "Проверка" };
function badge(st) { return `<span class="badge-st ${st}">${STLABEL[st] || st}</span>`; }
function proxyRow(it) {
  const ping = it.ping ? `<span class="ping">${it.ping} ms</span>` : "";
  const flag = it.country ? `<span class="flag">${esc(it.country)}</span>` : "";
  const bl = it.blacklist === false ? `<span class="ping" style="color:var(--error)">⚑BL</span>` : "";
  // Если прокси в блоклисте — он помечен мёртвым; поясняем это в подписи.
  const meta = it.blacklist === false
    ? `${esc((it.proto || "").toUpperCase())} · в блоклисте (DNSBL)`
    : `${esc((it.proto || "").toUpperCase())}${it.score ? " · score " + it.score : ""}`;
  return `<div class="li"><div class="grow"><div class="addr">${esc(it.addr)}</div>
    <div class="meta">${meta}</div></div>${flag}${bl}${ping}${badge(it.status)}</div>`;
}
function smtpRow(it) {
  const ping = it.ping ? `<span class="ping">${it.ping} ms</span>` : "";
  const err = it.error ? `<span class="err">${esc(it.error)}</span>` : `${esc(it.host)} · ${esc(it.enc)}${it.bound_proxy ? " · 🔗proxy" : ""}`;
  return `<div class="li"><div class="grow"><div class="addr">${esc(it.email)}</div>
    <div class="meta">${err}</div></div>${ping}${badge(it.status)}</div>`;
}

// проверка с опросом прогресса (страница обновляется живьём)
$("#px-check").addEventListener("click", () => runCheck("proxies"));
$("#sm-check").addEventListener("click", () => runCheck("smtp"));
// ползунки таймаута/потоков — живое число рядом + заливка трека до кружка акцентом
function fillRange(el) {
  const min = +el.min || 0, max = +el.max || 100, v = +el.value;
  const pct = max > min ? ((v - min) / (max - min)) * 100 : 0;
  el.style.setProperty("--fill", pct.toFixed(1) + "%");
}
["px", "sm"].forEach((p) => {
  [[$("#" + p + "-timeout"), p + "-timeout-val"], [$("#" + p + "-threads"), p + "-threads-val"]]
    .forEach(([el, valId]) => {
      if (!el) return;
      const upd = () => { $("#" + valId).textContent = el.value; fillRange(el); };
      el.addEventListener("input", upd);
      upd();  // инициализация: и число, и заливка под дефолтное значение
    });
});

// Полный лок UI на время проверки: нельзя грузить/настраивать/регулировать — только смотреть.
// Перечень всех интерактивных элементов (кроме вкладок и прокрутки списков).
const LOCK_SEL = [
  "[data-load]", "[data-clear]", "#px-check", "#sm-check", "#px-remove-dead", "#sm-remove-dead",
  "#px-timeout", "#px-threads", "#sm-timeout", "#sm-threads", ".pg-prev", ".pg-next",
  "#consistent", "#emailonly", "#open-preview", "#open-preview-2",
  "#cc", "#cc-pct", "#bcc", "#bcc-pct", "#control", "#control-n", "#plan-refresh",
  "#test-email", "#test-send", "#p-delay-min", "#p-delay-max", "#p-threads",
  "#btn-start", "#btn-pause", "#btn-stop", "#log-clear",
  "#resume-btn", "#resume-clear",
];
function setBusy(v) {
  _busy = v;
  document.body.classList.toggle("busy", v);
  LOCK_SEL.forEach((s) => $$(s).forEach((el) => { el.disabled = v; }));
  if (!v) {
    // Снять лок: вернуть условные состояния (кнопки настроек/пейджеры/отправка).
    pagers.proxies.refresh(); pagers.smtp.refresh();
    tick();
  }
}
$("#px-remove-dead").addEventListener("click", () => api().remove_dead_proxies().then(() => { pagers.proxies.reload(); refreshBadges(); }));
$("#sm-remove-dead").addEventListener("click", () => api().remove_dead_smtp().then(() => { pagers.smtp.reload(); refreshBadges(); }));

function setPct(p, pct) {
  $("#" + p + "-progress").style.width = pct + "%";
  $("#" + p + "-progress-pct").textContent = pct + "%";
}
function runCheck(kind) {
  const p = kind === "proxies" ? "px" : "sm";
  // Значения ползунков: таймаут (сек) и число потоков — передаём в проверку.
  const threads = +$("#" + p + "-threads").value;
  const timeout = +$("#" + p + "-timeout").value;
  api()["check_" + kind](threads, timeout).then((r) => {
    if (r.busy || r.empty) return;
    $("#" + p + "-progress-wrap").hidden = false;
    setPct(p, 0);
    setBusy(true);  // блокируем весь UI на время проверки
    pollCheck(kind);
  });
}
function pollCheck(kind) {
  const p = kind === "proxies" ? "px" : "sm";
  // refresh() перерисовывает ТЕКУЩУЮ страницу (её статусы меняются по мере проверки),
  // обновляет доступность кнопок (setSetupButtons) и возвращает running/done для %.
  pagers[kind].refresh().then((st) => {
    const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
    setPct(p, pct);
    if (st.running) setTimeout(() => pollCheck(kind), 700);
    else {
      setPct(p, 100);  // проверка завершена
      setBusy(false);  // снимаем лок UI
      setTimeout(() => { $("#" + p + "-progress-wrap").hidden = true; setPct(p, 0); }, 900);
      refreshBadges();
    }
  });
}

// ── Чекбоксы контента ───────────────────────────────────────────────────
$("#consistent").addEventListener("change", (e) => api().set_consistent_links(e.target.checked));
$("#emailonly").addEventListener("change", (e) => api().set_email_only(e.target.checked));

// ── Кампания: автосохранение конфига CC/BCC/контроль ────────────────────
let cfgTimer = null;
["cc", "cc-pct", "bcc", "bcc-pct", "control", "control-n"].forEach((id) =>
  $("#" + id).addEventListener("input", () => { clearTimeout(cfgTimer); cfgTimer = setTimeout(saveCampaignCfg, 400); }));
function saveCampaignCfg() {
  api().set_campaign_config({
    cc: $("#cc").value, cc_pct: $("#cc-pct").value,
    bcc: $("#bcc").value, bcc_pct: $("#bcc-pct").value,
    control: $("#control").value, control_every_n: $("#control-n").value,
  }).then((r) => setMsg("camp-cfg-msg", `✓ CC:${r.cc} · BCC:${r.bcc} · контроль:${r.control}`, "ok"));
}

// ── План ────────────────────────────────────────────────────────────────
$("#plan-refresh").addEventListener("click", refreshPlan);
function refreshPlan() {
  api().plan().then((r) => {
    $("#plan-alive").textContent = r.alive; $("#plan-total").textContent = r.total;
    // Потоки при отправке = min(живых, 50); показываем и подставляем именно это, чтобы план
    // не обещал больше, чем реально запустится. per_conn убран из отправки (авто-лимит по
    // домену), поэтому в плане его больше не показываем — иначе интерфейс врал бы про капот.
    const th = Math.min(r.threads || 0, 50);
    $("#plan-threads").textContent = th;
    $("#plan-text").textContent = r.text || "";
    const body = $("#plan-body"); body.innerHTML = "";
    if (!r.rows || !r.rows.length) { body.innerHTML = `<tr><td colspan="2" style="color:var(--dim2);text-align:center;padding:26px">—</td></tr>`; return; }
    r.rows.forEach((row) => { const tr = document.createElement("tr"); tr.innerHTML = `<td>${esc(row.email)}</td><td class="num">${row.count}</td>`; body.appendChild(tr); });
    $("#p-threads").value = th;
  });
}

// ── Отправка: тест, старт/пауза/стоп, лог ───────────────────────────────
$("#test-send").addEventListener("click", () => {
  const email = $("#test-email").value.trim();
  setMsg("test-msg", "Отправляю тест…", "warn");
  $("#test-send").disabled = true;
  api().send_test(email).then((r) => setMsg("test-msg", (r.ok ? "✓ " : "✗ ") + r.info, r.ok ? "ok" : "err"))
    .finally(() => ($("#test-send").disabled = false));
});
function gatherParams() {
  // Осталось три регулятора: диапазон задержки «от…до» и число потоков.
  // Прочее (разброс/писем-в-мин/на-коннект/на-аккаунт) убрано — дефолты задаёт мост.
  return {
    delay_min: $("#p-delay-min").value, delay_max: $("#p-delay-max").value,
    threads: $("#p-threads").value,
  };
}
$("#btn-start").addEventListener("click", () => {
  api().start_campaign(gatherParams()).then((r) => {
    if (r.error) { setMsg("test-msg", "✗ " + r.error, "err"); return; }
    tick();
  });
});
$("#btn-pause").addEventListener("click", () => {
  const paused = $("#btn-pause").dataset.paused === "1";
  (paused ? api().resume_campaign() : api().pause_campaign()).then(() => tick());
});
$("#btn-stop").addEventListener("click", () => api().stop_campaign().then(() => tick()));
$("#log-clear").addEventListener("click", () => { $("#console").innerHTML = `<div class="empty">Лог очищен</div>`; lastLogLen = 0; });

let lastLogLen = 0;
function renderLog(lines) {
  const c = $("#console");
  if (!lines || !lines.length) { if (!c.children.length || c.querySelector(".empty")) c.innerHTML = `<div class="empty">Лог появится после старта…</div>`; return; }
  if (lines.length < lastLogLen || c.querySelector(".empty")) { c.innerHTML = ""; lastLogLen = 0; }
  for (let i = lastLogLen; i < lines.length; i++) {
    const t = lines[i]; const cls = /✓/.test(t) ? "ok" : /✗|error|Error/.test(t) ? "err" : /Старт|Sending|Spawn|Stop/.test(t) ? "sys" : "";
    const d = document.createElement("div"); d.className = "l " + cls; d.textContent = t; c.appendChild(d);
  }
  lastLogLen = lines.length; c.scrollTop = c.scrollHeight;
}

// ── Возобновление прерванной кампании ───────────────────────────────────
function refreshResumeBanner() {
  api().queue_state().then((s) => {
    const b = $("#resume-banner");
    if (!s.exists) { b.classList.remove("show"); return; }
    $("#resume-text").textContent = `Найдена прерванная кампания: осталось ${s.remaining} из ${s.total}, отправлено ${s.sent} (${s.saved_at}).`;
    b.classList.add("show");
  });
}
$("#resume-btn").addEventListener("click", () => api().resume_from_state(gatherParams()).then((r) => {
  if (r.error) setMsg("test-msg", "✗ " + r.error, "err"); else { $("#resume-banner").classList.remove("show"); tick(); }
}));
$("#resume-clear").addEventListener("click", () => api().clear_state().then(() => $("#resume-banner").classList.remove("show")));

// ── Общий опрос состояния кампании (лог + статистика) ────────────────────
function setStatusPill(id, tId, snap, running, paused) {
  const pill = $("#" + id), t = $("#" + tId);
  pill.classList.remove("run", "pause", "stop");
  if (running && !paused) pill.classList.add("run");
  else if (paused) pill.classList.add("pause");
  else pill.classList.add("stop");
  t.textContent = snap.status_text || "Ожидание";
}
function tick() {
  if (!window.pywebview) return;
  api().campaign_state().then((s) => {
    const snap = s.snapshot || {};
    setStatusPill("send-status", "send-status-t", snap, s.running, s.paused);
    // Кап потоков = min(живых SMTP, 50): подписываем «макс N» и не даём ввести больше.
    const capN = Math.min(s.alive_smtp || 0, 50);
    const thLbl = $("#p-threads-lbl");
    if (thLbl) thLbl.textContent = capN ? `Потоки (макс ${capN})` : "Потоки (нет живых SMTP)";
    const thEl = $("#p-threads");
    if (thEl) { thEl.max = capN || 50; if (capN && thEl.value && +thEl.value > capN) thEl.value = capN; }
    $("#btn-start").disabled = s.running || !s.can_start;
    $("#btn-pause").disabled = !s.running;
    $("#btn-stop").disabled = !s.running;
    $("#btn-pause").dataset.paused = s.paused ? "1" : "0";
    $("#btn-pause").innerHTML = s.paused ? "▶ Продолжить" : "⏸ Пауза";
    renderLog(s.log);
    setStatusPill("st-status", "st-status-t", snap, s.running, s.paused);
    $("#st-started").textContent = "Старт: " + (snap.started_at || "—");
    $("#st-progress").style.width = Math.round((snap.progress || 0) * 100) + "%";
    $("#st-sent").textContent = snap.sent || 0; $("#st-of").textContent = " из " + (snap.total || 0);
    $("#st-errors").textContent = snap.errors || 0;
    $("#st-speed").textContent = snap.speed_per_min || 0;
    $("#st-remaining").textContent = snap.remaining || 0;
    $("#st-eta").textContent = snap.eta_min || 0;
    renderStatTable("st-smtp", (snap.smtp || []).map((x) => [x.email, x.sent, x.errors, x.status]));
    renderStatTable("st-proxy", (snap.proxy || []).map((x) => [x.address, x.used, x.errors, x.status]));
  });
}
function renderStatTable(id, rows) {
  const b = $("#" + id);
  if (!rows.length) { b.innerHTML = `<tr><td colspan="4" style="color:var(--dim2);text-align:center;padding:22px">Нет данных</td></tr>`; return; }
  b.innerHTML = rows.map((r) => `<tr><td style="max-width:170px;overflow:hidden;text-overflow:ellipsis">${esc(r[0])}</td>
    <td class="num">${r[1]}</td><td class="num" style="color:var(--error)">${r[2]}</td><td>${esc(r[3])}</td></tr>`).join("");
}
setInterval(() => { if (activeTab === "send" || activeTab === "stats") tick(); }, 1000);

// ── МОДАЛ ПРЕВЬЮ ПИСЬМА ─────────────────────────────────────────────────
const PV = { client: "gmail", device: "desktop", theme: "light", images: "on", index: -1, data: null };
const CLIENT_LABEL = { gmail: "Gmail", outlook: "Outlook", yahoo: "Yahoo", apple: "Apple Mail", mailru: "Mail.ru", yandex: "Yandex" };
const CLIENT_COLOR = { gmail: "#ea4335", outlook: "#0078d4", yahoo: "#6001d2", apple: "#555", mailru: "#005ff9", yandex: "#fc3f1d" };

$("#open-preview").addEventListener("click", openPreview);
$("#open-preview-2").addEventListener("click", openPreview);
$("#pv-close").addEventListener("click", () => $("#preview-overlay").classList.remove("show"));
$("#preview-overlay").addEventListener("click", (e) => { if (e.target.id === "preview-overlay") $("#preview-overlay").classList.remove("show"); });
$("#pv-reroll").addEventListener("click", () => loadPreview());
$("#pv-body").addEventListener("change", (e) => { PV.index = parseInt(e.target.value, 10); loadPreview(); });
segBind("pv-client", "c", (v) => { PV.client = v; applyChrome(); });
segBind("pv-device", "d", (v) => { PV.device = v; applyFrame(); });
segBind("pv-theme", "t", (v) => { PV.theme = v; applyFrame(); });
segBind("pv-images", "i", (v) => { PV.images = v; applyFrame(); });
function segBind(id, attr, cb) {
  $("#" + id).addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    $$("#" + id + " button").forEach((x) => x.classList.toggle("on", x === b));
    cb(b.dataset[attr]);
  });
}
function openPreview() {
  $("#preview-overlay").classList.add("show");
  api().body_titles().then((r) => {
    const sel = $("#pv-body"); sel.innerHTML = `<option value="-1">Случайное</option>` +
      (r.items || []).map((t) => `<option value="${t.index}">${esc(t.title)}</option>`).join("");
    sel.value = String(PV.index);
  });
  loadPreview();
}
function loadPreview() {
  $("#pv-loading").style.display = "block"; $("#pv-client-frame").style.display = "none";
  api().preview_email({ index: PV.index, name: "Анна", email: "anna@example.com" }).then((d) => {
    PV.data = d;
    $("#pv-from").textContent = d.from_name || d.from_email;
    $("#pv-subj").textContent = d.subject;
    $("#pv-pre").textContent = d.preheader || "— нет preheader —";
    $("#pv-avatar").textContent = (d.from_name || "?").trim().charAt(0).toUpperCase() || "?";
    $("#pv-format").textContent = d.format;
    const m = d.metrics || {};
    $("#pv-m-html").textContent = m.html_size || 0; $("#pv-m-text").textContent = m.text_len || 0;
    $("#pv-m-links").textContent = m.links || 0; $("#pv-m-img").textContent = m.images || 0;
    $("#pv-loading").style.display = "none"; $("#pv-client-frame").style.display = "block";
    applyChrome(); applyFrame();
  });
}
function applyChrome() {
  $("#pv-chrome-t").textContent = CLIENT_LABEL[PV.client];
  $("#pv-avatar").style.background = CLIENT_COLOR[PV.client] || "#7c8aa0";
}
function applyFrame() {
  const frame = $("#pv-client-frame"), main = $("#pv-main");
  const dark = PV.theme === "dark";
  frame.classList.toggle("mobile", PV.device === "mobile");
  frame.classList.toggle("dark", dark);
  main.classList.toggle("dark", dark);
  if (!PV.data) return;
  const doc = frameDoc(PV.data.html || "", dark, PV.images === "off");
  const ifr = $("#pv-frame");
  ifr.setAttribute("sandbox", "allow-same-origin");
  ifr.onload = () => { try { const h = ifr.contentDocument.body.scrollHeight; ifr.style.height = Math.min(Math.max(h + 6, 160), 900) + "px"; } catch (e) { ifr.style.height = "440px"; } };
  ifr.srcdoc = doc;
}
function frameDoc(html, dark, imagesOff) {
  const bg = dark ? "#1f2023" : "#ffffff", fg = dark ? "#e8e8ea" : "#1a1a1a";
  const link = dark ? "#7db3ff" : "#2563eb";
  const hide = imagesOff ? "img{display:none!important}" : "";
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0}body{background:${bg};color:${fg};font:14px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:18px;word-break:break-word}
    a{color:${link}} img{max-width:100%;height:auto} table{max-width:100%} ${hide}</style></head><body>${html}</body></html>`;
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#preview-overlay").classList.remove("show"); });

// ── Готовность моста ────────────────────────────────────────────────────
function onReady() {
  api().ping().then((r) => {
    const b = $("#bridge");
    b.innerHTML = `<span class="dot"></span>${r.ok ? "мост подключён" : "мост недоступен"}`;
    b.className = "bridge " + (r.ok ? "ok" : "err");
    refreshBadges(); pagers.proxies.reload(); pagers.smtp.reload(); refreshResumeBanner();
  });
}
if (window.pywebview) onReady();
else window.addEventListener("pywebviewready", onReady);

// ── DEV-заглушка моста (ТОЛЬКО при ?demo, когда pywebview отсутствует) ───
// Для визуальной проверки интерфейса и ПАГИНАЦИИ в обычном браузере без окна
// pywebview. В реальном запуске window.pywebview существует и этот блок не
// выполняется. Данные вымышленные, объёмы намеренно большие.
if (!window.pywebview && new URLSearchParams(location.search).has("demo")) {
  const P = (v) => Promise.resolve(v);
  const N_SUBJ = 5000, N_REC = 12000, N_PX = 3000, N_SM = 800, N_LINK = 100;
  const win = (arr, o, l) => { o = Math.max(0, Math.min(o | 0, arr.length)); l = l || 200; return { arr: arr.slice(o, o + l), off: o, lim: l, total: arr.length }; };
  const subj = Array.from({ length: N_SUBJ }, (_, i) => `{Привет|Здравствуй} {{name}}, {у меня|тут} {кое-что|новость} для тебя №${i + 1}`);
  const sndrs = ["Abigail", "Amanda", "Ashley", "Ava", "Avery", "Bella", "Chloe", "Emma", "Grace", "Hannah", "Isla", "Jasmine", "Katie", "Lily", "Mia", "Nora", "Olivia", "Paige", "Quinn", "Ruby", "Sofia", "Tara", "Uma", "Violet", "Willow", "Xena", "Yara", "Zoe", "Nadia"];
  const bodies = Array.from({ length: 7 }, (_, i) => `Тело письма #${i + 1} — {Привет|Хэй} {{name}}`);
  const links = Array.from({ length: N_LINK }, (_, i) => `https://example.com/offer?id=${1000 + i}&utm=mail`);
  const recips = Array.from({ length: N_REC }, (_, i) => ({ email: `user${i + 1}@gmail.com`, name: i % 3 ? "" : `Имя${i + 1}` }));
  const pxFinal = (i) => (i % 4 === 1 ? "dead" : "alive");  // статус ПОСЛЕ проверки (~25% мёртвых)
  // Часть SMTP после проверки остаётся «untested» — как в реале, когда проверку срывает
  // прокси/сеть (это НЕ значит «мёртвый»). Так демонстрируется, что такие «?» не мешают
  // удалять мёртвые.
  const smFinal = (i) => (i % 5 === 1 ? "dead" : i % 5 === 2 ? "untested" : "alive");
  const smErr = (i) => (smFinal(i) === "dead" ? "🔑 Bad Credentials: 535 auth failed"
    : smFinal(i) === "untested" ? "🌐 Proxy error: timed out" : "");
  const pxBL = (i) => i % 7 === 0;  // в блоклисте (DNSBL)
  // Политика владельца: живой-но-в-блоклисте = мёртвый. В demo сразу отражаем это в статусе.
  const pxStatus = (i) => (pxFinal(i) === "dead" || pxBL(i)) ? "dead" : "alive";
  let proxies = Array.from({ length: N_PX }, (_, i) => ({ addr: `104.28.${(i % 250)}.${(i % 99) + 1}:1080`, proto: "socks5", status: pxStatus(i), ping: pxStatus(i) === "alive" ? 150 + (i % 200) : 0, country: pxStatus(i) === "alive" ? "DE" : "", blacklist: pxBL(i) ? false : true, score: pxStatus(i) === "alive" ? 80 : 0 }));
  let smtps = Array.from({ length: N_SM }, (_, i) => ({ host: `smtp.mail${i}.com:587`, email: `sender${i + 1}@mail${i % 40}.com`, enc: "STARTTLS", status: smFinal(i), ping: smFinal(i) === "alive" ? 200 + (i % 120) : 0, error: smErr(i), bound_proxy: false }));
  let pxChecked = false, smChecked = false;  // «Проверить все» переводит в true
  let pxRun = false, smRun = false;  // окно «идёт проверка» (для наблюдаемого лока UI)
  const cnt = (arr) => ({ total: arr.length, alive: arr.filter((x) => x.status === "alive").length, dead: arr.filter((x) => x.status === "dead").length });
  // До проверки пул виден как «не пров.» (untested), после — с реальными статусами.
  const viewItems = (arr, ok) => ok ? arr : arr.map((x) => ({ ...x, status: "untested", ping: 0, country: "", error: "", blacklist: null }));
  const viewCnt = (arr, ok) => ok ? cnt(arr) : { total: arr.length, alive: 0, dead: 0 };
  const demoBody = `<table width="100%"><tr><td align="center"><table width="560" style="background:#fff;border-radius:12px;overflow:hidden;font-family:Arial">
    <tr><td style="background:#4ade80;padding:22px 28px;color:#08160c;font-size:22px;font-weight:800">Привет, Анна 👋</td></tr>
    <tr><td style="padding:26px 28px;color:#333;font-size:15px;line-height:1.6">Мы приготовили кое-что для тебя. Загляни, пока действует.<br><br>
    <a href="https://example.com/x" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:13px 26px;border-radius:8px;font-weight:700">Открыть предложение</a></td></tr>
    </table></td></tr></table>`;
  const legendLinks = `[[LINK]] (${N_LINK})`;
  const mock = {
    ping: () => P({ ok: true, app: "SMTP MAILER (demo)" }),
    status: () => P({ subjects: N_SUBJ, bodies: 7, senders: sndrs.length, links: N_LINK, recipients: N_REC, proxies: viewCnt(proxies, pxChecked), smtp: viewCnt(smtps, smChecked) }),
    page_content: (kind, o, l) => {
      const src = kind === "subjects" ? subj : kind === "senders" ? sndrs : kind === "bodies" ? bodies : kind === "links" ? links : [];
      const w = win(src, o, l);
      const out = { kind, total: w.total, offset: w.off, limit: w.lim, text: w.arr.join("\n") || "(пусто)" };
      if (kind === "links") out.legend = legendLinks;
      return P(out);
    },
    page_recipients: (o, l) => { const w = win(recips, o, l); return P({ total: w.total, offset: w.off, limit: w.lim, rows: w.arr }); },
    page_proxies: (o, l) => { const it = viewItems(proxies, pxChecked); const w = win(it, o, l); return P({ ...viewCnt(proxies, pxChecked), offset: w.off, limit: w.lim, items: w.arr, running: pxRun, done: pxRun ? Math.floor(proxies.length * 0.4) : (pxChecked ? proxies.length : 0) }); },
    page_smtp: (o, l) => { const it = viewItems(smtps, smChecked); const w = win(it, o, l); return P({ ...viewCnt(smtps, smChecked), offset: w.off, limit: w.lim, items: w.arr, running: smRun, done: smRun ? Math.floor(smtps.length * 0.4) : (smChecked ? smtps.length : 0) }); },
    pick_and_load: (kind) => {
      const t = { subjects: N_SUBJ, bodies: 7, senders: sndrs.length, recipients: N_REC };
      if (kind === "links") return P({ files: [{ file: "links.txt", macro: "[[LINK]]", count: N_LINK }], total: N_LINK, mode: "urls" });
      if (kind === "proxies") return P({ added: N_PX, ...viewCnt(proxies, pxChecked) });
      if (kind === "smtp") return P({ added: N_SM, ...viewCnt(smtps, smChecked) });
      return P({ added: t[kind] || 0, total: t[kind] || 0 });
    },
    clear_subjects: () => P({ total: 0 }), clear_bodies: () => P({ total: 0 }), clear_senders: () => P({ total: 0 }),
    clear_links: () => P({ files: [], total: 0 }), clear_recipients: () => P({ total: 0 }),
    clear_proxies: () => { proxies = []; pxChecked = false; return P({ total: 0, alive: 0, dead: 0 }); },
    clear_smtp: () => { smtps = []; smChecked = false; return P({ total: 0, alive: 0, dead: 0 }); },
    remove_dead_proxies: () => { proxies = proxies.filter((x) => x.status !== "dead"); return P({ removed: 0, ...viewCnt(proxies, pxChecked) }); },
    remove_dead_smtp: () => { smtps = smtps.filter((x) => x.status !== "dead"); return P({ removed: 0, ...viewCnt(smtps, smChecked) }); },
    check_proxies: () => { pxChecked = true; pxRun = true; setTimeout(() => { pxRun = false; }, 1500); return P({ started: true, total: proxies.length, threads: 30, timeout: 10 }); },
    check_smtp: () => { smChecked = true; smRun = true; setTimeout(() => { smRun = false; }, 1500); return P({ started: true, total: smtps.length, threads: 30, timeout: 15 }); },
    check_progress: (k) => { const ok = k === "proxies" ? pxChecked : smChecked; const arr = k === "proxies" ? proxies : smtps; return P({ running: false, done: ok ? arr.length : 0, ...viewCnt(arr, ok) }); },
    set_consistent_links: () => P({ ok: true }), set_email_only: () => P({ ok: true }),
    set_campaign_config: () => P({ ok: true, cc: 2, bcc: 1, control: 1 }),
    body_titles: () => P({ items: bodies.map((b, i) => ({ index: i, title: b.slice(0, 40) })) }),
    preview_email: () => P({ from_name: "Мария Соколова", from_email: "sender1@mail1.com", subject: "Анна, у нас для тебя кое-что есть", preheader: "Загляни, пока предложение действует", html: demoBody, is_html: true, format: "HTML", metrics: { html_size: 980, text_len: 120, links: 1, images: 0 }, bodies: 7, subjects: N_SUBJ }),
    plan: () => P({ alive: 2, total: N_REC, rows: [{ email: "sender1@mail1.com", count: N_REC / 2 }, { email: "sender2@mail2.com", count: N_REC / 2 }], text: `2 отправителя разошлют ровно по ${N_REC / 2} писем.`, threads: 2, per_conn: N_REC / 2 }),
    send_test: () => P({ ok: true, info: "отправлено за 1.8 сек через sender1@mail1.com" }),
    queue_state: () => P({ exists: false }),
    campaign_state: () => P({ snapshot: { status_text: "Ожидание", sent: 0, errors: 0, total: 0, remaining: 0, running: false, paused: false, started_at: "—", speed_per_min: 0, eta_min: 0, progress: 0, smtp: [], proxy: [] }, log: [], running: false, paused: false, recipients: N_REC, alive_smtp: cnt(smtps).alive, can_start: true }),
  };
  window.pywebview = { api: mock };
  onReady();
}
