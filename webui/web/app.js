const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const api = () => window.pywebview.api;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function setMsg(id, text, cls) {
  const el = $("#" + id); if (!el) return;
  el.textContent = text || ""; el.className = "msg" + (cls ? " " + cls : "");
}


let activeTab = "setup";
let _busy = false;
$("#tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab"); if (!btn) return;
  activeTab = btn.dataset.tab;
  $$(".tab").forEach((t) => t.classList.toggle("active", t === btn));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === activeTab));
  onTabEnter(activeTab);
});

function onTabEnter(tab) {
  if (tab === "setup") { pagers.proxies.reload(); pagers.smtp.reload(); updateCheckClocks(); }
  else if (tab === "content") { ["subjects", "bodies", "senders", "links"].forEach((k) => pagers[k].reload()); refreshContentIssues(); }
  else if (tab === "campaign") { pagers.recipients.reload(); saveCampaignCfg(); refreshPresets(); }
  else if (tab === "plan") refreshPlan();
  else if (tab === "send") { refreshResumeBanner(); tick(); }
  else if (tab === "stats") tick();
}


function refreshBadges() {
  api().status().then((s) => {
    $("#tb-setup").textContent = s.smtp.alive;
    $("#tb-content").textContent = s.bodies;
    $("#tb-campaign").textContent = s.recipients;
  });
}


function makePager(opts) {
  const foot = $("#" + opts.footId);
  const state = { offset: 0, limit: 200, total: 0 };
  function updateFoot() {
    if (!foot) return;
    const from = state.total ? state.offset + 1 : 0;
    const to = Math.min(state.offset + state.limit, state.total);
    foot.querySelector(".pg-label").textContent = `${from}–${to} из ${state.total}`;


    foot.querySelector(".pg-prev").disabled = state.offset <= 0;
    foot.querySelector(".pg-next").disabled = state.offset + state.limit >= state.total;
    foot.hidden = state.total <= state.limit;
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


function renderContent(kind, r) {
  const pre = $("#" + kind + "-preview");
  if (kind === "links") {
    pre.textContent = (r.legend ? r.legend + "\n\n" : "") + (r.text || "(пусто)");
  } else {
    pre.textContent = r.text || "(пусто)";
  }
}

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

  if (kind === "subjects" || kind === "bodies" || kind === "senders") $("#" + kind + "-count").textContent = r.total || 0;
  else if (kind === "links") $("#links-count").textContent = (r.files ? r.files.length : 0);
  else if (kind === "recipients") $("#recipients-count").textContent = r.total || 0;
  if (pagers[kind]) pagers[kind].reload();
  if (kind === "subjects" || kind === "bodies") refreshContentIssues();
  refreshBadges();
}


function fmtIssues(list) {
  if (!list || !list.length) return "";
  const parts = list.slice(0, 8).map((x) => `#${x.n} (${x.why})`);
  const more = list.length > 8 ? ` … и ещё ${list.length - 8}` : "";
  return `⚠ ${list.length} шаблон(ов) с ошибкой спинтакса — получатель увидит сырой «{ … | … }»: ${parts.join(", ")}${more}. Почини их, иначе брак уйдёт в письмо.`;
}
function refreshContentIssues() {
  api().content_issues().then((r) => {
    const sw = $("#subjects-warn"), bw = $("#bodies-warn");
    const st = fmtIssues(r.subjects), bt = fmtIssues(r.bodies);
    if (sw) { sw.textContent = st; sw.hidden = !st; }
    if (bw) { bw.textContent = bt; bw.hidden = !bt; }
  }).catch(() => {});
}


function renderList(kind, r) {
  const p = kind === "proxies" ? "px" : "sm";
  $("#" + p + "-total").textContent = r.total || 0;
  if (kind === "proxies") {

    $("#px-clean").textContent = r.clean || 0;
    $("#px-dirty").textContent = r.dirty || 0;
  } else {
    $("#sm-alive").textContent = r.alive || 0;
  }
  $("#" + p + "-dead").textContent = r.dead || 0;
  const untested = (r.total || 0) - (r.alive || 0) - (r.dead || 0);
  $("#" + p + "-untested").textContent = untested < 0 ? 0 : untested;
  setSetupButtons(kind, r);
  updateProgress(p, r);
  const list = $("#" + p + "-list");
  const items = r.items || [];
  if (!items.length) {
    list.innerHTML = `<div class="empty">${kind === "proxies" ? "Прокси не загружены" : "SMTP-аккаунты не загружены"}</div>`;
    return;
  }
  list.innerHTML = items.map((it) => kind === "proxies" ? proxyRow(it) : smtpRow(it)).join("");
}


function setSetupButtons(kind, r) {
  const p = kind === "proxies" ? "px" : "sm";
  const total = r.total || 0, alive = r.alive || 0, dead = r.dead || 0, running = !!r.running;
  const loaded = total > 0;
  const busyk = running || _busy;
  $("#" + p + "-check").disabled = !loaded || busyk;
  $("#" + p + "-clear").disabled = !loaded || busyk;


  const rd = $("#" + p + "-remove-dead");
  rd.disabled = !(loaded && !busyk && dead > 0);
  rd.title = dead > 0
    ? `Удалить ${dead} мёртвых (непроверенные «?» не трогаем — их можно перепроверить)`
    : "Мёртвых аккаунтов нет — удалять нечего";


  const untested = Math.max(0, total - alive - dead);
  const rc = $("#" + p + "-recheck-untested");
  if (rc) {
    rc.disabled = !(loaded && !busyk && untested > 0);
    rc.title = untested > 0
      ? `Перепроверить ${untested} непроверенных заново (живых/мёртвых не трогает)`
      : "Непроверенных нет";
  }
  const ru = $("#" + p + "-remove-untested");
  if (ru) {
    ru.disabled = !(loaded && !busyk && untested > 0);
    ru.title = untested > 0
      ? `Удалить ${untested} непроверенных «?» (мёртвых/живых не трогает)`
      : "Непроверенных нет — удалять нечего";
  }

  const cp = $("#" + p + "-copy-all");
  if (cp) cp.disabled = !(loaded && !busyk);

  if (kind === "proxies") {
    const rb = $("#px-remove-blacklisted");
    if (rb) {
      const dirty = r.dirty || 0;
      rb.disabled = !(loaded && !busyk && dirty > 0);
      rb.title = dirty > 0
        ? `Удалить ${dirty} живых прокси из чёрных списков (DNSBL)`
        : "Прокси в чёрных списках нет";
    }
  }
}
const STLABEL = { alive: "Живой", dead: "Мёртвый", untested: "?", checking: "Проверка" };
function badge(st) { return `<span class="badge-st ${st}">${STLABEL[st] || st}</span>`; }
function proxyRow(it) {
  const ping = it.ping ? `<span class="ping">${it.ping} ms</span>` : "";
  const flag = it.country ? `<span class="flag">${esc(it.country)}</span>` : "";
  let meta;
  if (it.status === "dead" && it.error) {


    meta = `<span class="err">${esc(it.error)}</span>`;
  } else if (it.blacklist === false) {
    meta = `${esc((it.proto || "").toUpperCase())} · в блоклисте (DNSBL)`;
  } else {
    meta = `${esc((it.proto || "").toUpperCase())}${it.score ? " · score " + it.score : ""}`;
  }


  const stBadge = (it.status === "alive" && it.blacklist === false)
    ? `<span class="badge-st blacklist">⚑ Блэклист</span>`
    : badge(it.status);
  const exitInfo = (it.exit_ip && !it.addr.startsWith(it.exit_ip)) ? ` → ${esc(it.exit_ip)}` : "";
  return `<div class="li"><div class="grow"><div class="addr">${esc(it.addr)}${exitInfo}</div>
    <div class="meta">${meta}</div></div>${flag}${ping}${stBadge}</div>`;
}
function smtpRow(it) {
  const ping = it.ping ? `<span class="ping">${it.ping} ms</span>` : "";
  const err = it.error ? `<span class="err">${esc(it.error)}</span>` : `${esc(it.host)} · ${esc(it.enc)}${it.bound_proxy ? " · 🔗proxy" : ""}`;


  const via = it.proxy
    ? `<div class="meta via">🌐 проверен через ${esc(it.proxy)}</div>` : "";


  const listed = (it.blacklist === false) || (it.domain_blacklist === false);
  const zones = (it.bl_zones && it.bl_zones.length) ? " (" + it.bl_zones.slice(0, 3).map(esc).join(", ") + ")" : "";
  const bl = listed ? `<span class="ping" style="color:var(--error)" title="в чёрных списках${zones}">⚑BL</span>` : "";
  return `<div class="li"><div class="grow"><div class="addr">${esc(it.email)}</div>
    <div class="meta">${err}</div>${via}</div>${bl}${ping}${badge(it.status)}</div>`;
}


$("#px-check").addEventListener("click", () => runCheck("proxies"));
$("#sm-check").addEventListener("click", () => runCheck("smtp"));

$("#px-recheck-untested").addEventListener("click", () => runCheck("proxies", true));
$("#sm-recheck-untested").addEventListener("click", () => runCheck("smtp", true));

$("#px-load-url").addEventListener("click", () => {
  const url = (window.prompt("URL со списком прокси (по строке на прокси):") || "").trim();
  if (!url) return;
  $("#px-load-url").disabled = true;
  api().load_proxies_url(url)
    .then((r) => { if (r && r.error) { console.error("load_proxies_url:", r.error); return; }
      pagers.proxies.reload(); refreshBadges(); })
    .finally(() => ($("#px-load-url").disabled = false));
});

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
      upd();
    });
});


const LOCK_SEL = [
  '[data-panel="setup"] [data-load]', '[data-panel="setup"] [data-clear]',
  "#px-load-url", "#px-check", "#sm-check", "#px-remove-dead", "#sm-remove-dead",
  "#px-remove-blacklisted",
  "#px-recheck-untested", "#sm-recheck-untested", "#px-remove-untested", "#sm-remove-untested",
  "#px-copy-all", "#sm-copy-all",
  "#px-timeout", "#px-threads", "#sm-timeout", "#sm-threads",
];
function setBusy(v) {
  _busy = v;
  document.body.classList.toggle("busy", v);
  LOCK_SEL.forEach((s) => $$(s).forEach((el) => { el.disabled = v; }));
  if (!v) {

    pagers.proxies.refresh(); pagers.smtp.refresh();
    tick();
  }
}
$("#px-remove-dead").addEventListener("click", () => api().remove_dead_proxies().then(() => { pagers.proxies.reload(); refreshBadges(); }));

$("#px-remove-blacklisted").addEventListener("click", () => api().remove_blacklisted_proxies().then(() => { pagers.proxies.reload(); refreshBadges(); }));
$("#sm-remove-dead").addEventListener("click", () => api().remove_dead_smtp().then(() => { pagers.smtp.reload(); refreshBadges(); }));

$("#px-remove-untested").addEventListener("click", () => api().remove_untested_proxies().then(() => { pagers.proxies.reload(); refreshBadges(); }));
$("#sm-remove-untested").addEventListener("click", () => api().remove_untested_smtp().then(() => { pagers.smtp.reload(); refreshBadges(); }));

$("#px-copy-all").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const r = await api().export_proxies_raw();
  if (!r || !r.count) return;
  const ok = await copyText(r.text);
  flashCopied(btn, ok);
});
$("#sm-copy-all").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const r = await api().export_smtp_raw();
  if (!r || !r.count) return;
  const ok = await copyText(r.text);
  flashCopied(btn, ok);
});

function setPct(p, pct) {
  $("#" + p + "-progress").style.width = pct + "%";
  $("#" + p + "-progress-pct").textContent = pct + "%";
}


function updateProgress(p, r) {
  const total = r.total || 0, alive = r.alive || 0, dead = r.dead || 0;
  const untested = Math.max(0, total - alive - dead);
  const running = !!r.running, done = r.done || 0, chkTotal = r.check_total || 0;
  const wrap = $("#" + p + "-progress-wrap");


  const ranThisSession = chkTotal > 0;
  const show = total > 0 && (running || ranThisSession || untested < total);
  wrap.hidden = !show;
  if (!show) { setPct(p, 0); return; }
  let pct;
  if (running) {
    pct = chkTotal ? Math.min(99, Math.max(0, Math.floor(done / chkTotal * 100))) : 0;
  } else if (ranThisSession) {

    pct = 100;
  } else {

    pct = total ? Math.min(100, Math.floor((total - untested) / total * 100)) : 0;
  }
  setPct(p, pct);
}


const checkTimers = {
  proxies: { everRan: false, running: false, startMs: 0, endMs: 0 },
  smtp: { everRan: false, running: false, startMs: 0, endMs: 0 },
};
function fmtDateTime(dt) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(dt.getDate())}.${p(dt.getMonth() + 1)}.${dt.getFullYear()} ${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
}
function startCheckTimer(kind) {
  checkTimers[kind] = { everRan: true, running: true, startMs: Date.now(), endMs: 0 };
  updateCheckClocks();
}
function stopCheckTimer(kind) {
  const t = checkTimers[kind];
  if (t.everRan && t.running) { t.running = false; t.endMs = Date.now(); }
  updateCheckClocks();
}
function updateCheckClocks() {
  ["proxies", "smtp"].forEach((kind) => {
    const p = kind === "proxies" ? "px" : "sm";
    const w = $("#" + p + "-check-when"), d = $("#" + p + "-check-dur");
    if (!w || !d) return;
    const t = checkTimers[kind];
    if (!t.everRan) {

      w.textContent = fmtDateTime(new Date()); w.className = "live";
      d.textContent = "—"; d.className = "";
      return;
    }
    w.textContent = fmtDateTime(new Date(t.startMs)); w.className = "";
    const endMs = t.running ? Date.now() : t.endMs;
    d.textContent = fmtClock(Math.max(0, Math.floor((endMs - t.startMs) / 1000)));
    d.className = t.running ? "run" : "done";
  });
}
function runCheck(kind, onlyUntested) {
  const p = kind === "proxies" ? "px" : "sm";

  const threads = +$("#" + p + "-threads").value;
  const timeout = +$("#" + p + "-timeout").value;

  api()["check_" + kind](threads, timeout, !!onlyUntested).then((r) => {
    if (r.busy || r.empty) return;
    startCheckTimer(kind);
    setBusy(true);
    pollCheck(kind);
  });
}
function pollCheck(kind) {
  const p = kind === "proxies" ? "px" : "sm";


  pagers[kind].refresh().then((st) => {
    if (st.running) { updateCheckClocks(); setTimeout(() => pollCheck(kind), 700); }
    else {


      stopCheckTimer(kind);
      setBusy(false);
      refreshBadges();
    }
  });
}


$("#consistent").addEventListener("change", (e) => api().set_consistent_links(e.target.checked));
$("#emailonly").addEventListener("change", (e) => api().set_email_only(e.target.checked));


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


function fillPresetList(items, selected) {
  const sel = $("#preset-list");
  sel.innerHTML = (items && items.length)
    ? items.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")
    : `<option value="">— нет сохранённых —</option>`;
  if (selected) sel.value = selected;
}
function refreshPresets() {
  api().list_campaign_presets().then((r) => fillPresetList(r.items));
}
$("#preset-save").addEventListener("click", () => {
  const name = $("#preset-name").value.trim();
  if (!name) { setMsg("preset-msg", "Укажи имя пресета", "warn"); return; }
  api().save_campaign_preset(name).then((r) => {
    if (r.error) { setMsg("preset-msg", "✗ " + r.error, "err"); return; }
    fillPresetList(r.items, r.name);
    setMsg("preset-msg", `✓ Сохранён «${r.name}»`, "ok");
  });
});
$("#preset-load").addEventListener("click", () => {
  const name = $("#preset-list").value;
  if (!name) { setMsg("preset-msg", "Нет пресета для загрузки", "warn"); return; }
  api().load_campaign_preset(name).then((r) => {
    if (r.error) { setMsg("preset-msg", "✗ " + r.error, "err"); return; }
    $("#cc").value = r.cc || ""; $("#cc-pct").value = r.cc_pct || 0;
    $("#bcc").value = r.bcc || ""; $("#bcc-pct").value = r.bcc_pct || 0;
    $("#control").value = r.control || ""; $("#control-n").value = r.control_every_n || 0;
    $("#consistent").checked = !!r.consistent_links; $("#emailonly").checked = !!r.email_only;
    setMsg("preset-msg", `✓ Загружен «${r.name}»`, "ok");
  });
});


$("#plan-refresh").addEventListener("click", refreshPlan);
function refreshPlan() {
  api().plan().then((r) => {
    $("#plan-alive").textContent = r.alive; $("#plan-total").textContent = r.total;


    const th = Math.min(r.threads || 0, 50);
    $("#plan-threads").textContent = th;
    $("#plan-text").textContent = r.text || "";
    const body = $("#plan-body"); body.innerHTML = "";
    if (!r.rows || !r.rows.length) { body.innerHTML = `<tr><td colspan="2" style="color:var(--dim2);text-align:center;padding:26px">—</td></tr>`; return; }
    r.rows.forEach((row) => { const tr = document.createElement("tr"); tr.innerHTML = `<td>${esc(row.email)}</td><td class="num">${row.count}</td>`; body.appendChild(tr); });
    $("#p-threads").value = th;
  });
}


$("#test-send").addEventListener("click", () => {
  const email = $("#test-email").value.trim();
  setMsg("test-msg", "Отправляю тест…", "warn");
  $("#test-send").disabled = true;
  api().send_test(email).then((r) => setMsg("test-msg", (r.ok ? "✓ " : "✗ ") + r.info, r.ok ? "ok" : "err"))
    .finally(() => ($("#test-send").disabled = false));
});

$("#test-clear").addEventListener("click", () => {
  const el = $("#test-email"); el.value = ""; el.focus(); setMsg("test-msg", "", "");
});
function gatherParams() {


  return {
    delay_min: $("#p-delay-min").value, delay_max: $("#p-delay-max").value,
    threads: $("#p-threads").value,
    bind_proxy: !!($("#p-bind-proxy") && $("#p-bind-proxy").checked),
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


let lastAlive = 0, lastRecip = 0;
const SEND_OVERHEAD_SEC = 1.2;
function fmtDur(sec) {
  sec = Math.max(0, Math.round(sec));
  const d = Math.floor(sec / 86400); sec -= d * 86400;
  const h = Math.floor(sec / 3600); sec -= h * 3600;
  const m = Math.floor(sec / 60);
  if (d > 0) return `${d}д ${h}ч`;
  if (h > 0) return `${h}ч ${m}м`;
  if (m > 0) return `${m}м`;
  return "<1м";
}
function fmtWhen(date) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(date.getDate())}.${p(date.getMonth() + 1)} ${p(date.getHours())}:${p(date.getMinutes())}`;
}
function updateEstimate() {
  const es = $("#est-speed"), ed = $("#est-dur"), ef = $("#est-finish"), en = $("#est-note");
  if (!es) return;
  const a = parseFloat($("#p-delay-min").value) || 0;
  const b = parseFloat($("#p-delay-max").value) || 0;
  const cap = Math.min(lastAlive || 0, 50);
  const thIn = parseInt($("#p-threads").value, 10);
  let workers = cap;
  if (thIn > 0) workers = Math.min(thIn, cap);
  if (!workers) {
    es.textContent = "—"; ed.textContent = "—"; ef.textContent = "—";
    en.textContent = "Нет живых SMTP — проверь аккаунты во вкладке «Настройки».";
    return;
  }
  let avg = (a + b) / 2, autoNote = "";
  if (avg <= 0) { avg = 6; autoNote = "Задержка 0 → авто-профиль по домену (взято ≈6 с). "; }
  const avgDelay = Math.max(0.5, avg);
  const steadyPerMin = workers * 60 / (avgDelay + SEND_OVERHEAD_SEC);
  const recip = lastRecip || 0;
  if (!recip) {


    es.textContent = "—"; ed.textContent = "—"; ef.textContent = "—";
    en.textContent = autoNote + "Загрузи базу получателей — без неё скорость не оценить (в начале её сильно снижает прогрев).";
    return;
  }


  const WARM_FULL = 100;
  const nPerWorker = Math.max(1, Math.round(recip / workers));
  const warmCount = Math.min(nPerWorker, WARM_FULL);
  let workerSec = 0;
  for (let k = 0; k < warmCount; k++)
    workerSec += avgDelay * (1 + 2 * Math.exp(-4 * k / WARM_FULL)) + SEND_OVERHEAD_SEC;
  workerSec += (nPerWorker - warmCount) * (avgDelay + SEND_OVERHEAD_SEC);
  const totalSec = workerSec;


  const effPerMin = totalSec > 0 ? recip / (totalSec / 60) : steadyPerMin;
  es.textContent = Math.max(1, Math.round(effPerMin));
  ed.textContent = fmtDur(totalSec);
  ef.textContent = fmtWhen(new Date(Date.now() + totalSec * 1000));
  en.textContent = autoNote + `${workers} воркер(ов) × ${recip} получателей. Учтён прогрев по кривой движка — первые письма ~×3 медленнее, оценка средняя.`;
}


function fmtClock(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
}
["p-delay-min", "p-delay-max", "p-threads"].forEach((id) => {
  const el = $("#" + id); if (el) el.addEventListener("input", updateEstimate);
});

let lastLogLen = 0;
function renderLog(lines) {
  const c = $("#console");
  if (!lines || !lines.length) { if (!c.children.length || c.querySelector(".empty")) c.innerHTML = `<div class="empty">Лог появится после старта…</div>`; return; }


  const atBottom = (c.scrollHeight - c.scrollTop - c.clientHeight) < 48;
  let reset = false;
  if (lines.length < lastLogLen || c.querySelector(".empty")) { c.innerHTML = ""; lastLogLen = 0; reset = true; }
  for (let i = lastLogLen; i < lines.length; i++) {
    const t = lines[i]; const cls = /✓|✅|🏁/.test(t) ? "ok" : /✗|❌|⛔|error|Error/.test(t) ? "err" : /▶|⚙|🔌|↻|⏳/.test(t) ? "sys" : "";
    const d = document.createElement("div"); d.className = "l " + cls; d.textContent = t; c.appendChild(d);
  }
  lastLogLen = lines.length;
  if (atBottom || reset) c.scrollTop = c.scrollHeight;
}


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

    lastAlive = s.alive_smtp || 0; lastRecip = s.recipients || 0;
    updateEstimate();


    const secs = Math.max(0, Math.floor(snap.elapsed_sec || 0));
    const clock = fmtClock(secs);
    const running = s.running && !s.paused;
    const finished = !s.running && (snap.sent || 0) + (snap.errors || 0) > 0;
    const stt = $("#st-timer"); if (stt) stt.textContent = clock;
    const swt = $("#send-timer");
    if (swt) {
      swt.textContent = "⏱ " + clock;
      swt.classList.remove("run", "done");
      if (running) swt.classList.add("run");
      else if (finished) swt.classList.add("done");
    }
  });
}
function renderStatTable(id, rows) {
  const b = $("#" + id);
  if (!rows.length) { b.innerHTML = `<tr><td colspan="4" style="color:var(--dim2);text-align:center;padding:22px">Нет данных</td></tr>`; return; }
  b.innerHTML = rows.map((r) => `<tr><td style="max-width:170px;overflow:hidden;text-overflow:ellipsis">${esc(r[0])}</td>
    <td class="num">${r[1]}</td><td class="num" style="color:var(--error)">${r[2]}</td><td>${esc(r[3])}</td></tr>`).join("");
}
setInterval(() => {
  if (activeTab === "send" || activeTab === "stats") tick();
  else if (activeTab === "setup") updateCheckClocks();
}, 1000);


const PV = { client: "gmail", device: "desktop", theme: "light", images: "on", index: -1, data: null };


const CLIENTS = {
  gmail: { accent: "#c5221f", me: "я", logo: '<span class="mark">M</span>Gmail', search: "Поиск в почте",
    folders: [["✉", "Входящие", "on"], ["★", "Помеченные"], ["🕗", "Отложенные"], ["➤", "Отправленные"], ["🗎", "Черновики"]],
    label: "Входящие", to: "кому: я ▾", acts: [["↩", "Ответить"], ["↪", "Переслать"]] },
  outlook: { accent: "#0f6cbd", brand: "#0f6cbd", me: "Вы", logo: '<span class="mark">◨</span>Outlook', search: "Поиск",
    sidehdr: "Избранное",
    folders: [["📥", "Входящие", "on"], ["➤", "Отправленные"], ["🗎", "Черновики"], ["🗑", "Удалённые"], ["🗂", "Архив"]],
    label: "Входящие", to: "Кому: Вы", acts: [["↩", "Ответить"], ["⇉", "Ответить всем"], ["↪", "Переслать"]] },
  yahoo: { accent: "#6001d2", brand: "#5f01d1", me: "мне", logo: 'Yahoo! <b>Почта</b>', search: "Поиск в почте",
    folders: [["📥", "Входящие", "on"], ["●", "Непрочитанные"], ["★", "Помеченные"], ["🗎", "Черновики"], ["➤", "Отправленные"], ["⚠", "Спам"]],
    label: "Входящие", to: "кому: мне", acts: [["↩", "Ответить"], ["↪", "Переслать"]] },
  apple: { accent: "#1a73e8", mac: true, me: "я",
    folders: [["📥", "Входящие", "on"], ["🚩", "Флажки"], ["➤", "Отправленные"], ["🗑", "Корзина"], ["🗂", "Архив"]],
    label: "Входящие", to: "Кому: я", acts: [["↩", "Ответить"], ["⇉", "Ответить всем"], ["↪", "Переслать"]] },
  mailru: { accent: "#0a5cff", me: "вам", logo: '<span class="mark">@</span>Почта&nbsp;Mail', search: "Поиск по почте",
    folders: [["📥", "Входящие", "on"], ["➤", "Отправленные"], ["🗎", "Черновики"], ["⚠", "Спам"], ["🗑", "Корзина"]],
    label: "Входящие", to: "кому: вам", acts: [["↩", "Ответить"], ["↪", "Переслать"]] },
  yandex: { accent: "#ff3333", me: "вам", logo: '<span class="mark">Я</span>Почта', search: "Поиск в письмах",
    folders: [["📥", "Входящие", "on"], ["➤", "Отправленные"], ["🗑", "Удалённые"], ["⚠", "Спам"], ["🗎", "Черновики"]],
    label: "Входящие", to: "кому: вам", acts: [["↩", "Ответить"], ["↪", "Переслать"]] },
};

$("#open-preview").addEventListener("click", openPreview);
$("#open-preview-2").addEventListener("click", openPreview);
$("#pv-close").addEventListener("click", () => $("#preview-overlay").classList.remove("show"));
$("#preview-overlay").addEventListener("click", (e) => { if (e.target.id === "preview-overlay") $("#preview-overlay").classList.remove("show"); });
$("#pv-reroll").addEventListener("click", () => loadPreview());
$("#pv-body").addEventListener("change", (e) => { PV.index = parseInt(e.target.value, 10); loadPreview(); });

segBind("pv-client", "c", (v) => { PV.client = v; renderPreview(); });
segBind("pv-device", "d", (v) => { PV.device = v; renderPreview(); });
segBind("pv-theme", "t", (v) => { PV.theme = v; renderPreview(); });
segBind("pv-images", "i", (v) => { PV.images = v; renderPreview(); });
function segBind(id, attr, cb) {
  $("#" + id).addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    $$("#" + id + " button").forEach((x) => x.classList.toggle("on", x === b));
    cb(b.dataset[attr]);
  });
}


async function copyText(text) {
  text = text == null ? "" : String(text);


  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_to_clipboard) {
      const r = await window.pywebview.api.copy_to_clipboard(text);
      if (r && r.ok) return true;
    }
  } catch (e) {}

  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}

  try {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.top = "-1000px"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.focus(); ta.select();
    const ok = document.execCommand("copy"); document.body.removeChild(ta); return ok;
  } catch (e) { return false; }
}
function flashCopied(btn, ok) {
  if (!btn) return;
  const prev = btn.dataset.label || btn.textContent;
  btn.dataset.label = prev;
  btn.classList.add(ok ? "copied" : "copyfail");
  btn.textContent = ok ? "✅ Скопировано!" : "⚠ Скопируй вручную";
  setTimeout(() => { btn.textContent = prev; btn.classList.remove("copied", "copyfail"); delete btn.dataset.label; }, 2000);
}

function pvBodySource() {
  const d = PV.data || {};
  return d.is_html ? (d.html || "") : (d.text || "");
}
function pvFieldValue(kind) {
  const d = PV.data || {};
  if (kind === "body") return pvBodySource();
  return d[kind] != null ? String(d[kind]) : "";
}
async function pvCopy(kind, btn) {
  if (!PV.data) return;
  const ok = await copyText(pvFieldValue(kind));
  if (!ok && kind === "body") showCodePanel();
  flashCopied(btn, ok);
}
function showCodePanel() {
  const wrap = $("#pv-code-wrap"), ta = $("#pv-code");
  if (!wrap || !ta) return;
  ta.value = pvBodySource();
  wrap.hidden = false;
  ta.focus(); ta.select();
}
$("#pv-copy-code").addEventListener("click", (e) => pvCopy("body", e.currentTarget));
$("#pv-toggle-code").addEventListener("click", () => {
  const wrap = $("#pv-code-wrap");
  if (wrap.hidden) showCodePanel(); else wrap.hidden = true;
});
$("#pv-code-copy").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const ta = $("#pv-code"); ta.focus(); ta.select();
  flashCopied(btn, await copyText(ta.value));
});
$("#pv-code-hide").addEventListener("click", () => { $("#pv-code-wrap").hidden = true; });

$("#pv-score-checks-btn").addEventListener("click", () => {
  const box = $("#pv-score-checks"), btn = $("#pv-score-checks-btn");
  box.hidden = !box.hidden;
  btn.textContent = box.hidden ? "Показать чек-лист" : "Скрыть чек-лист";
});


$("#pv-variance-btn").addEventListener("click", () => {
  const box = $("#pv-variance"), btn = $("#pv-variance-btn");
  box.hidden = false; box.innerHTML = `<div class="note">Считаю 40 вариантов…</div>`;
  btn.disabled = true;
  api().score_variants(40).then((r) => {
    btn.disabled = false;
    if (!r || !r.available) { box.innerHTML = `<div class="note">Разброс не посчитать: ${esc((r && r.reason) || "нет данных")}</div>`; return; }
    const gcol = (v) => v >= 66 ? "#4ade80" : v >= 50 ? "#fbbf24" : "#f87171";
    const w = r.worst || {};
    box.innerHTML = `<div class="pv-var-row">
        <span class="v" style="color:${gcol(r.min)}">min ${r.min}</span>
        <span class="v">медиана ${r.median}</span>
        <span class="v" style="color:${gcol(r.max)}">max ${r.max}</span>
        <span class="n">по ${r.count}</span></div>
      <div class="pv-var-worst"><b>Худший вариант (${w.overall}/${esc(w.grade || "")}):</b>
        <div class="s">тема: «${esc(w.subject || "")}»</div>
        ${(w.fails || []).slice(0, 5).map((f) => `<div class="it">− ${esc(f)}</div>`).join("")}</div>
      <div class="note">Разброс = разные раскрытия спинтакса. Чем ближе min к max, тем стабильнее шаблоны.</div>`;
  }).catch((e) => { btn.disabled = false; box.innerHTML = `<div class="note">Ошибка: ${esc(String(e))}</div>`; });
});
$$("[data-copy]").forEach((b) => b.addEventListener("click", (e) => pvCopy(b.dataset.copy, e.currentTarget)));

function openPreview() {
  $("#preview-overlay").classList.add("show");
  api().body_titles().then((r) => {
    const sel = $("#pv-body"); sel.innerHTML = `<option value="-1">Случайное</option>` +
      (r.items || []).map((t) => `<option value="${t.index}">${esc(t.title)}</option>`).join("");
    sel.value = String(PV.index);
  });
  refreshCombos();
  loadPreview();
}


function refreshCombos() {
  const all = $("#pv-combo-all"), grand = $("#pv-combo-grand");
  if (!all) return;
  api().combinations().then((r) => {
    all.textContent = r.body_total || "—";
    grand.textContent = (r.grand_total && r.subjects)
      ? `Всего писем (тема×текст×имя): ${r.grand_total}`
      : "Загрузи темы и имена — покажу полный охват кампании.";
  }).catch(() => {});
}
function loadPreview() {
  $("#pv-loading").style.display = "block"; $("#pv-client-frame").style.display = "none";


  api().preview_email({ index: PV.index }).then((d) => {
    PV.data = d;
    $("#pv-format").textContent = d.format;
    const m = d.metrics || {};
    $("#pv-m-html").textContent = m.html_size || 0; $("#pv-m-text").textContent = m.text_len || 0;
    $("#pv-m-links").textContent = m.links || 0; $("#pv-m-img").textContent = m.images || 0;
    $("#pv-combo-body").textContent = d.combinations || "—";

    const iss = (d.subject_issue || []).concat(d.body_issue || []);
    const w = $("#pv-warn");
    if (w) {
      if (iss.length) { w.hidden = false; w.textContent = "⚠ Показанный шаблон УЙДЁТ ПОЛУЧАТЕЛЮ БИТЫМ (ошибка спинтакса: " + iss.join(", ") + "). Именно так письмо и придёт — сырой «{ … | … }». Почини шаблон в контенте."; }
      else { w.hidden = true; }
    }


    const hint = $("#pv-hint");
    if (hint) {
      if (d.no_recipients) { hint.hidden = false; hint.textContent = "ℹ База получателей не загружена — имя {{name}} в превью пустое. Загрузи базу во вкладке «Кампания»: тогда в письме будет реальное имя из неё, разное у каждого получателя."; }
      else { hint.hidden = true; }
    }
    $("#pv-loading").style.display = "none"; $("#pv-client-frame").style.display = "block";
    renderScore(d.score);
    $("#pv-variance").hidden = true;
    renderPreview();
    if (!$("#pv-code-wrap").hidden) $("#pv-code").value = pvBodySource();
  });
}


function renderScore(s) {
  const box = $("#pv-score"), checksBtn = $("#pv-score-checks-btn"), checksBox = $("#pv-score-checks");
  if (!box) return;
  checksBox.hidden = true; checksBtn.textContent = "Показать чек-лист";
  if (!s) { box.innerHTML = `<div class="note">Загрузите темы и тела — тогда посчитаю оценку.</div>`; checksBtn.hidden = true; return; }
  if (s.error) { box.innerHTML = `<div class="note">Оценка недоступна: ${esc(s.error)}</div>`; checksBtn.hidden = true; return; }
  const bar = (label, v) => {
    const col = v >= 70 ? "#4ade80" : v >= 50 ? "#fbbf24" : "#f87171";
    return `<div class="pv-sc-bar"><span class="l">${label}</span>
      <span class="tr"><span class="fl" style="width:${v}%;background:${col}"></span></span><b>${v}</b></div>`;
  };
  const ce = s.ctr_estimate || {};
  let html = `<div class="pv-sc-top">
      <div class="pv-sc-grade" style="color:${s.grade_color};border-color:${s.grade_color}">${esc(s.grade)}</div>
      <div class="pv-sc-num"><b>${s.overall}</b><span>/100</span>
        <div class="pv-sc-ctr">CTR ~ ${esc(ce.val || "?")} <span class="${ce.up ? "up" : "dn"}">${esc(ce.tag || "")}</span></div></div>
    </div>
    ${bar("Доставляемость", s.deliverability)}
    ${bar("Открываемость", s.openrate)}
    ${bar("Кликабельность", s.clickability)}
    <div class="pv-sc-verdict">${esc(s.verdict || "")}</div>`;
  const c = s.contrast || {};
  if (c && c.ok === false) html += `<div class="pv-sc-flag bad">${esc(c.text)}</div>`;
  else if (c && c.ratio) html += `<div class="pv-sc-flag ok">✓ ${esc(c.text)}</div>`;

  const st = s.structure || {};
  if (st.issues && st.issues.length) {
    html += `<div class="pv-sc-struct"><b>Структура ${typeof st.score === "number" ? st.score : ""}:</b> ` +
      st.issues.slice(0, 4).map((i) => `<div class="it ${esc(i.t || "")}">${esc(i.text)}</div>`).join("") + `</div>`;
  }
  box.innerHTML = html;

  const rows = [];
  const groups = [["Открываемость", "openrate"], ["Кликабельность", "clickability"], ["Доставляемость", "deliverability"]];
  const ch = s.checks || {};
  for (const [title, key] of groups) {
    rows.push(`<div class="pv-ck-h">${title}</div>`);
    for (const it of (ch[key] || []))
      rows.push(`<div class="pv-ck ${it.ok ? "y" : "n"}">${it.ok ? "＋" : "−"} ${esc(it.text)}</div>`);
  }
  checksBox.innerHTML = rows.join("");
  checksBtn.hidden = false;
}

function renderPreview() {
  if (!PV.data) return;
  const dark = PV.theme === "dark", mobile = PV.device === "mobile", imagesOff = PV.images === "off";
  const cfg = CLIENTS[PV.client] || CLIENTS.gmail;
  const mount = $("#pv-client-frame"), main = $("#pv-main");
  mount.classList.toggle("mobile", mobile);
  main.classList.toggle("dark", dark);
  mount.innerHTML = clientHTML(PV.client, cfg, PV.data, dark, mobile);
  const ifr = $("#pv-frame");
  if (!ifr) return;
  ifr.setAttribute("sandbox", "allow-same-origin");

  ifr.onload = () => { try { const h = ifr.contentDocument.body.scrollHeight; ifr.style.height = Math.min(Math.max(h + 8, 200), 820) + "px"; } catch (e) { ifr.style.height = "460px"; } };
  ifr.srcdoc = frameDoc(PV.data.html || "", dark, imagesOff);
}
function pvFolders(cfg) {
  return (cfg.folders || []).map((f) =>
    `<div class="m-fold${f[2] === "on" ? " on" : ""}"><span class="ic">${f[0]}</span><span>${esc(f[1])}</span></div>`).join("");
}
function clientHTML(key, cfg, d, dark, mobile) {
  const fromName = esc(d.from_name || d.from_email || "Отправитель");
  const fromEmail = esc(d.from_email || "");
  const subject = esc(d.subject || "(без темы)");
  const initial = ((d.from_name || d.from_email || "?").trim().charAt(0) || "?").toUpperCase();
  const vars = `--m-accent:${cfg.accent}` + (cfg.brand ? `;--m-topbg:${cfg.brand};--m-topfg:#fff` : "");
  const cls = `mailui ${key}${dark ? " dark" : ""}${mobile ? " mobile" : ""}`;
  const iframe = `<div class="m-frame-wrap"><iframe id="pv-frame" class="pv-frame" title="preview" sandbox=""></iframe></div>`;


  if (mobile) {
    const acts = (cfg.acts || []).map((a) => `<span class="i">${a[0]}</span>`).join("") + `<span class="i">🗑</span>`;
    return `<div class="${cls}" style="${vars}">
      <div class="m-topm">‹ ${esc(cfg.label || "Входящие")}<span class="m-me" style="margin-left:auto">${initial}</span></div>
      <div class="m-hdr"><div class="m-ava">${initial}</div><div class="m-who">
        <div class="m-fromrow"><span class="m-from">${fromName}</span><span class="m-date">сейчас</span></div>
        <div class="m-to">${esc(cfg.to || "кому: я")}</div></div></div>
      <div class="m-subj">${subject}</div>
      ${iframe}
      <div class="m-tools">${acts}</div>
    </div>`;
  }


  if (cfg.mac) {
    const tools = `<span class="i">🗑</span><span class="i">🚩</span><span class="i">🗂</span><span class="sp"></span>` +
      (cfg.acts || []).map((a) => `<span class="i" title="${esc(a[1])}">${a[0]}</span>`).join("");
    return `<div class="${cls}" style="${vars}">
      <div class="m-top mac"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span><span class="title">${esc(cfg.label || "Входящие")} — 24 сообщения</span></div>
      <div class="m-body">
        <div class="m-side"><div class="m-sidehdr">Ящики</div>${pvFolders(cfg)}</div>
        <div class="m-read">
          <div class="m-tools">${tools}</div>
          <div class="m-applehdr"><div class="m-ava">${initial}</div>
            <div class="m-who"><div class="m-from">${fromName} <span class="addr">&lt;${fromEmail}&gt;</span></div>
              <div class="m-subj2">${subject}</div><div class="m-to">${esc(cfg.to || "Кому: я")}</div></div>
            <div class="m-date">Сегодня, сейчас</div></div>
          ${iframe}
        </div>
      </div>
    </div>`;
  }


  const brandCls = cfg.brand ? " brand" : "";
  const tools = `<span class="i">←</span><span class="i">🗄</span><span class="i">⚠</span><span class="i">🗑</span><span class="sp"></span><span class="i">↩</span><span class="i">↪</span><span class="i">⋮</span>`;
  const acts = (cfg.acts || []).map((a, i) => `<span class="m-btn${i === 0 ? " pri" : ""}">${a[0]} ${esc(a[1])}</span>`).join("");
  return `<div class="${cls}" style="${vars}">
    <div class="m-top${brandCls}"><span class="burger">☰</span><span class="m-logo">${cfg.logo || esc(key)}</span>
      <span class="m-search">🔍 ${esc(cfg.search || "Поиск")}</span><span class="m-me">${initial}</span></div>
    <div class="m-body">
      <div class="m-side"><div class="m-compose">✏️ Написать</div>${cfg.sidehdr ? `<div class="m-sidehdr">${esc(cfg.sidehdr)}</div>` : ""}${pvFolders(cfg)}</div>
      <div class="m-read">
        <div class="m-tools">${tools}</div>
        <div class="m-subj">${subject} <span class="m-label">${esc(cfg.label || "Входящие")}</span></div>
        <div class="m-hdr"><div class="m-ava">${initial}</div><div class="m-who">
          <div class="m-fromrow"><span class="m-from">${fromName} <span class="addr">&lt;${fromEmail}&gt;</span></span><span class="m-date">сейчас</span></div>
          <div class="m-to">${esc(cfg.to || "кому: я")}</div></div></div>
        ${iframe}
        <div class="m-acts">${acts}</div>
      </div>
    </div>`;
}
function frameDoc(html, dark, imagesOff) {
  const bg = dark ? "#1f2023" : "#ffffff", fg = dark ? "#e8e8ea" : "#202124";
  const link = dark ? "#8ab4f8" : "#1a56db";
  const hide = imagesOff ? "img{display:none!important}" : "";


  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    html,body{margin:0;padding:0}
    body{background:${bg};color:${fg};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}
    img{max-width:100%;height:auto} a{color:${link}} ${hide}</style></head><body>${html}</body></html>`;
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#preview-overlay").classList.remove("show"); });


function onReady() {
  api().ping().then((r) => {
    const b = $("#bridge");
    b.innerHTML = `<span class="dot"></span>${r.ok ? "мост подключён" : "мост недоступен"}`;
    b.className = "bridge " + (r.ok ? "ok" : "err");
    refreshBadges(); pagers.proxies.reload(); pagers.smtp.reload(); refreshResumeBanner();
    updateCheckClocks();
  });
}
if (window.pywebview) onReady();
else window.addEventListener("pywebviewready", onReady);


if (!window.pywebview && new URLSearchParams(location.search).has("demo")) {
  const P = (v) => Promise.resolve(v);
  const N_SUBJ = 5000, N_REC = 12000, N_PX = 3000, N_SM = 800, N_LINK = 100;
  const win = (arr, o, l) => { o = Math.max(0, Math.min(o | 0, arr.length)); l = l || 200; return { arr: arr.slice(o, o + l), off: o, lim: l, total: arr.length }; };
  const subj = Array.from({ length: N_SUBJ }, (_, i) => `{Привет|Здравствуй} {{name}}, {у меня|тут} {кое-что|новость} для тебя №${i + 1}`);
  const sndrs = ["Abigail", "Amanda", "Ashley", "Ava", "Avery", "Bella", "Chloe", "Emma", "Grace", "Hannah", "Isla", "Jasmine", "Katie", "Lily", "Mia", "Nora", "Olivia", "Paige", "Quinn", "Ruby", "Sofia", "Tara", "Uma", "Violet", "Willow", "Xena", "Yara", "Zoe", "Nadia"];
  const bodies = Array.from({ length: 7 }, (_, i) => `Тело письма #${i + 1} — {Привет|Хэй} {{name}}`);
  const links = Array.from({ length: N_LINK }, (_, i) => `https://example.com/offer?id=${1000 + i}&utm=mail`);
  const recips = Array.from({ length: N_REC }, (_, i) => ({ email: `user${i + 1}@gmail.com`, name: i % 3 ? "" : `Имя${i + 1}` }));
  const pxFinal = (i) => (i % 4 === 1 ? "dead" : "alive");


  const smFinal = (i) => (i % 5 === 1 ? "dead" : i % 5 === 2 ? "untested" : "alive");
  const smErr = (i) => (smFinal(i) === "dead" ? "🔑 Bad Credentials: 535 auth failed"
    : smFinal(i) === "untested" ? "🌐 Proxy error: timed out" : "");
  const pxBL = (i) => i % 7 === 0;

  const pxStatus = (i) => (pxFinal(i) === "dead") ? "dead" : "alive";


  const pxErr = (i) => pxStatus(i) !== "dead" ? ""
    : (i % 8 === 1 ? "smtp.gmail.com:587 не прислал '220' — IP прокси, вероятно, в бане у почтовика"
      : "прокси не отвечает: SOCKS-подключение отклонено (порт закрыт или прокси мёртв)");
  let proxies = Array.from({ length: N_PX }, (_, i) => ({ addr: `104.28.${(i % 250)}.${(i % 99) + 1}:1080`, proto: "socks5", status: pxStatus(i), ping: pxStatus(i) === "alive" ? 150 + (i % 200) : (i % 8 === 1 ? 171 : 0), country: pxStatus(i) === "alive" ? "DE" : "", blacklist: pxBL(i) ? false : true, score: pxStatus(i) === "alive" ? 80 : 0, error: pxErr(i) }));

  const smProxy = (i) => (i % 6 === 3 ? "прямое соединение" : `185.${20 + (i % 60)}.${i % 250}.${(i % 99) + 1}:1080`);
  let smtps = Array.from({ length: N_SM }, (_, i) => ({ host: `smtp.mail${i}.com:587`, email: `sender${i + 1}@mail${i % 40}.com`, enc: "STARTTLS", status: smFinal(i), ping: smFinal(i) === "alive" ? 200 + (i % 120) : 0, error: smErr(i), bound_proxy: false, proxy: smProxy(i) }));
  let pxChecked = false, smChecked = false;
  let pxRun = false, smRun = false;
  let pxDone = 0, smDone = 0;

  const cnt = (arr) => ({ total: arr.length, alive: arr.filter((x) => x.status === "alive").length, dead: arr.filter((x) => x.status === "dead").length, clean: arr.filter((x) => x.status === "alive" && x.blacklist !== false).length, dirty: arr.filter((x) => x.status === "alive" && x.blacklist === false).length });

  const viewItems = (arr, ok) => ok ? arr : arr.map((x) => ({ ...x, status: "untested", ping: 0, country: "", error: "", blacklist: null, proxy: "" }));
  const viewCnt = (arr, ok) => ok ? cnt(arr) : { total: arr.length, alive: 0, dead: 0, clean: 0, dirty: 0 };


  const cntN = (arr, n) => { const d = arr.slice(0, n); return { total: arr.length, alive: d.filter((x) => x.status === "alive").length, dead: d.filter((x) => x.status === "dead").length, clean: d.filter((x) => x.status === "alive" && x.blacklist !== false).length, dirty: d.filter((x) => x.status === "alive" && x.blacklist === false).length }; };
  const itemsN = (arr, n) => arr.map((x, i) => i < n ? x : ({ ...x, status: "untested", ping: 0, country: "", error: "", blacklist: null, proxy: "" }));
  const demoBody = `<table width="100%"><tr><td align="center"><table width="560" style="background:#fff;border-radius:12px;overflow:hidden;font-family:Arial">
    <tr><td style="background:#4ade80;padding:22px 28px;color:#08160c;font-size:22px;font-weight:800">Привет 👋</td></tr>
    <tr><td style="padding:26px 28px;color:#333;font-size:15px;line-height:1.6">Мы приготовили кое-что для тебя. Загляни, пока действует.<br><br>
    <a href="https://example.com/x" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:13px 26px;border-radius:8px;font-weight:700">Открыть предложение</a></td></tr>
    </table></td></tr></table>`;
  const legendLinks = `[[LINK]] (${N_LINK})`;
  const mock = {
    ping: () => P({ ok: true, app: "Pinion (demo)" }),
    status: () => P({ subjects: N_SUBJ, bodies: 7, senders: sndrs.length, links: N_LINK, recipients: N_REC, proxies: viewCnt(proxies, pxChecked), smtp: viewCnt(smtps, smChecked) }),
    page_content: (kind, o, l) => {
      const src = kind === "subjects" ? subj : kind === "senders" ? sndrs : kind === "bodies" ? bodies : kind === "links" ? links : [];
      const w = win(src, o, l);
      const out = { kind, total: w.total, offset: w.off, limit: w.lim, text: w.arr.join("\n") || "(пусто)" };
      if (kind === "links") out.legend = legendLinks;
      return P(out);
    },
    page_recipients: (o, l) => { const w = win(recips, o, l); return P({ total: w.total, offset: w.off, limit: w.lim, rows: w.arr }); },
    page_proxies: (o, l) => {

      if (pxRun) { pxDone = Math.min(proxies.length, pxDone + Math.max(1, Math.ceil(proxies.length / 6))); if (pxDone >= proxies.length) { pxRun = false; pxChecked = true; } }
      const n = pxChecked ? proxies.length : (pxRun ? pxDone : 0);
      const w = win(itemsN(proxies, n), o, l);
      return P({ ...cntN(proxies, n), offset: w.off, limit: w.lim, items: w.arr, running: pxRun, done: n, check_total: (pxChecked || pxRun) ? proxies.length : 0 });
    },
    page_smtp: (o, l) => {
      if (smRun) { smDone = Math.min(smtps.length, smDone + Math.max(1, Math.ceil(smtps.length / 6))); if (smDone >= smtps.length) { smRun = false; smChecked = true; } }
      const n = smChecked ? smtps.length : (smRun ? smDone : 0);
      const w = win(itemsN(smtps, n), o, l);
      return P({ ...cntN(smtps, n), offset: w.off, limit: w.lim, items: w.arr, running: smRun, done: n, check_total: (smChecked || smRun) ? smtps.length : 0 });
    },
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
    remove_blacklisted_proxies: () => { proxies = proxies.filter((x) => !(x.status === "alive" && x.blacklist === false)); return P({ removed: 0, ...viewCnt(proxies, pxChecked) }); },
    remove_dead_smtp: () => { smtps = smtps.filter((x) => x.status !== "dead"); return P({ removed: 0, ...viewCnt(smtps, smChecked) }); },


    remove_untested_proxies: () => { proxies = proxies.filter((x) => x.status !== "untested"); return P({ removed: 0, ...viewCnt(proxies, pxChecked) }); },
    remove_untested_smtp: () => { smtps = smtps.filter((x) => x.status !== "untested"); return P({ removed: 0, ...viewCnt(smtps, smChecked) }); },
    export_proxies_raw: () => P({ text: proxies.map((x) => x.addr).join("\n"), count: proxies.length }),
    export_smtp_raw: () => P({ text: smtps.map((x) => x.host + ":" + x.email + ":password123").join("\n"), count: smtps.length }),


    check_proxies: (_t, _to, _ou) => { pxChecked = false; pxRun = true; pxDone = 0; return P({ started: true, total: proxies.length, threads: 30, timeout: 10 }); },
    check_smtp: (_t, _to, _ou) => { smChecked = false; smRun = true; smDone = 0; return P({ started: true, total: smtps.length, threads: 30, timeout: 15 }); },
    check_progress: (k) => { const ok = k === "proxies" ? pxChecked : smChecked; const arr = k === "proxies" ? proxies : smtps; return P({ running: false, done: ok ? arr.length : 0, ...viewCnt(arr, ok) }); },
    set_consistent_links: () => P({ ok: true }), set_email_only: () => P({ ok: true }),
    set_campaign_config: () => P({ ok: true, cc: 2, bcc: 1, control: 1 }),
    list_campaign_presets: () => P({ items: ["demo-пресет"] }),
    save_campaign_preset: (name) => P({ ok: true, name: name || "preset", items: ["demo-пресет", name || "preset"] }),
    load_campaign_preset: (name) => P({ ok: true, name, cc: "cc@x.com", bcc: "", cc_pct: 20, bcc_pct: 0, control: "me@x.com", control_every_n: 5, consistent_links: true, email_only: false }),
    load_proxies_url: () => P({ added: 0, total: proxies.length, alive: 0, dead: 0 }),
    body_titles: () => P({ items: bodies.map((b, i) => ({ index: i, title: b.slice(0, 40) })) }),
    preview_email: () => P({ from_name: "Мария Соколова", from_email: "sender1@mail1.com", subject: "у нас для тебя кое-что есть", preheader: "Загляни, пока предложение действует", html: demoBody, text: "hey, I saved something for you. take a look: https://example.com/offer", is_html: true, format: "HTML", no_recipients: false, metrics: { html_size: 980, text_len: 120, links: 1, images: 0 }, bodies: 7, subjects: N_SUBJ, subject_issue: [], body_issue: [], combinations: "≈ 2.4·10^5", score: { overall: 62, grade: "B", grade_color: "#86efac", deliverability: 100, openrate: 48, clickability: 55, verdict: "Письмо рабочее, но есть точки роста.", ctr_estimate: { val: "0.6-1.0%", tag: "↓ чуть ниже нормы", up: false, norm: "0.8-1.5%" }, checks: { openrate: [{ ok: true, text: "Личное обращение в теме: есть" }, { ok: false, text: "Вопрос в теме: нет" }], clickability: [{ ok: true, text: "Длина тела: 120 симв. (норма 50-600)" }, { ok: false, text: "Анкор без глагола: \"take a look\"" }], deliverability: [{ ok: true, text: "Длина темы: 30 симв. (норма 20-70)" }] }, tips: [], issues: [], contrast: { ok: true, ratio: 8.1, text: "Контраст в норме (минимум 8.1:1)" }, structure: { score: 92, status: "отлично", issues: [{ t: "info", text: "Нет <meta charset> — не страшно (MIME задаёт utf-8)" }] }, vertical: "dating", anchor: "take a look" } }),
    score_variants: () => P({ available: true, count: 40, min: 41, median: 58, max: 79, worst: { overall: 41, grade: "D", subject: "you almost missed this...", anchor: "take a look", fails: ["Конкретика / интрига в теме: нет", "Вопрос в теме: нет", "Эмодзи в теме: нет", "Призыв к действию: нет", "Анкор без глагола: \"take a look\""] } }),

    content_issues: () => P({ subjects: [], bodies: [{ n: 3, why: "незакрытая { ×1 (демо)" }] }),
    combinations: () => P({ bodies: 7, subjects: N_SUBJ, senders: sndrs.length, body_total: "≈ 8.4·10^9", subject_total: "1 280", grand_total: "≈ 3.1·10^16" }),
    plan: () => P({ alive: 2, total: N_REC, rows: [{ email: "sender1@mail1.com", count: N_REC / 2 }, { email: "sender2@mail2.com", count: N_REC / 2 }], text: `2 отправителя разошлют ровно по ${N_REC / 2} писем.`, threads: 2, per_conn: N_REC / 2 }),
    send_test: () => P({ ok: true, info: "отправлено за 1.8 сек через sender1@mail1.com" }),
    queue_state: () => P({ exists: false }),
    campaign_state: () => P({ snapshot: { status_text: "Ожидание", sent: 0, errors: 0, total: 0, remaining: 0, running: false, paused: false, started_at: "—", elapsed_sec: 0, speed_per_min: 0, eta_min: 0, progress: 0, smtp: [], proxy: [] }, log: [], running: false, paused: false, recipients: N_REC, alive_smtp: cnt(smtps).alive, can_start: true }),
  };
  window.pywebview = { api: mock };
  onReady();
}
