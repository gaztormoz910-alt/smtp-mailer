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
  else if (tab === "content") { ["subjects", "bodies", "senders", "links"].forEach((k) => pagers[k].reload()); refreshContentIssues(); }
  else if (tab === "campaign") { pagers.recipients.reload(); saveCampaignCfg(); refreshPresets(); }
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
    // Пагинация РАБОТАЕТ и во время проверки — стрелки гасим только по границам страниц,
    // без оглядки на _busy (владелец хочет листать данные, пока идёт проверка).
    foot.querySelector(".pg-prev").disabled = state.offset <= 0;
    foot.querySelector(".pg-next").disabled = state.offset + state.limit >= state.total;
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
  if (kind === "subjects" || kind === "bodies") refreshContentIssues();
  refreshBadges();
}

// Предупреждение о битых шаблонах (непарные скобки/«|» вне блока → уйдёт получателю сырым).
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

// ── Прокси / SMTP: рендер страницы (счётчики + окно элементов) ──────────
function renderList(kind, r) {
  const p = kind === "proxies" ? "px" : "sm";
  $("#" + p + "-total").textContent = r.total || 0;
  if (kind === "proxies") {
    // Прокси: живые делятся на ЧИСТЫХ (в рассылку) и В БЛЭКЛИСТЕ (не используются).
    $("#px-clean").textContent = r.clean || 0;
    $("#px-dirty").textContent = r.dirty || 0;
  } else {
    $("#sm-alive").textContent = r.alive || 0;
  }
  $("#" + p + "-dead").textContent = r.dead || 0;
  const untested = (r.total || 0) - (r.alive || 0) - (r.dead || 0);
  $("#" + p + "-untested").textContent = untested < 0 ? 0 : untested;
  setSetupButtons(kind, r);
  updateProgress(p, r);  // бар/% ведём из тех же счётчиков (100% ТОЛЬКО при непроверенных=0)
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
  // Непроверенные «?»: их можно ПЕРЕПРОВЕРИТЬ (через рабочие прокси) или УДАЛИТЬ отдельно.
  // Активны только когда непроверенные реально есть и не идёт проверка.
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
}
const STLABEL = { alive: "Живой", dead: "Мёртвый", untested: "?", checking: "Проверка" };
function badge(st) { return `<span class="badge-st ${st}">${STLABEL[st] || st}</span>`; }
function proxyRow(it) {
  const ping = it.ping ? `<span class="ping">${it.ping} ms</span>` : "";
  const flag = it.country ? `<span class="flag">${esc(it.country)}</span>` : "";
  // Блэклист НЕ убивает прокси: живой-в-блоклисте остаётся живым (метка ⚑BL), get_next его
  // просто не выбирает. Поэтому ⚑BL — метка, а не причина смерти.
  const bl = it.blacklist === false ? `<span class="ping" style="color:var(--error)">⚑BL</span>` : "";
  let meta;
  if (it.status === "dead" && it.error) {
    // Мёртвый прокси теперь объясняет ПОЧЕМУ (как SMTP-аккаунт с last_error). Так «171 ms +
    // Мёртвый» перестаёт быть парадоксом: рядом стоит причина (пинг — время открытия туннеля,
    // а мёртв — из-за провала SMTP-рукопожатия).
    meta = `<span class="err">${esc(it.error)}</span>`;
  } else if (it.blacklist === false) {
    meta = `${esc((it.proto || "").toUpperCase())} · в блоклисте (DNSBL)`;
  } else {
    meta = `${esc((it.proto || "").toUpperCase())}${it.score ? " · score " + it.score : ""}`;
  }
  return `<div class="li"><div class="grow"><div class="addr">${esc(it.addr)}</div>
    <div class="meta">${meta}</div></div>${flag}${bl}${ping}${badge(it.status)}</div>`;
}
function smtpRow(it) {
  const ping = it.ping ? `<span class="ping">${it.ping} ms</span>` : "";
  const err = it.error ? `<span class="err">${esc(it.error)}</span>` : `${esc(it.host)} · ${esc(it.enc)}${it.bound_proxy ? " · 🔗proxy" : ""}`;
  // Через какой прокси проверялся аккаунт (второй строкой, приглушённо). "прямое соединение"
  // — проверка шла без прокси. Пусто, пока аккаунт не проверялся.
  const via = it.proxy
    ? `<div class="meta via">🌐 проверен через ${esc(it.proxy)}</div>` : "";
  return `<div class="li"><div class="grow"><div class="addr">${esc(it.email)}</div>
    <div class="meta">${err}</div>${via}</div>${ping}${badge(it.status)}</div>`;
}

// проверка с опросом прогресса (страница обновляется живьём)
$("#px-check").addEventListener("click", () => runCheck("proxies"));
$("#sm-check").addEventListener("click", () => runCheck("smtp"));
// «Перепроверить не пров.» — перегоняет ТОЛЬКО непроверенные (живых/мёртвых не трогает).
$("#px-recheck-untested").addEventListener("click", () => runCheck("proxies", true));
$("#sm-recheck-untested").addEventListener("click", () => runCheck("smtp", true));
// Загрузка прокси по URL (метод моста load_proxies_url уже был — не хватало кнопки).
$("#px-load-url").addEventListener("click", () => {
  const url = (window.prompt("URL со списком прокси (по строке на прокси):") || "").trim();
  if (!url) return;
  $("#px-load-url").disabled = true;
  api().load_proxies_url(url)
    .then((r) => { if (r && r.error) { console.error("load_proxies_url:", r.error); return; }
      pagers.proxies.reload(); refreshBadges(); })
    .finally(() => ($("#px-load-url").disabled = false));
});
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

// Лок UI на время проверки: нельзя грузить/настраивать/регулировать/стартовать рассылку.
// ИСКЛЮЧЕНИЕ — пагинация (.pg-prev/.pg-next): листать страницы данных МОЖНО прямо во время
// проверки (по просьбе владельца). Вкладки и прокрутка списков тоже не блокируются.
const LOCK_SEL = [
  "[data-load]", "[data-clear]", "#px-load-url", "#px-check", "#sm-check", "#px-remove-dead", "#sm-remove-dead",
  "#px-recheck-untested", "#sm-recheck-untested", "#px-remove-untested", "#sm-remove-untested",
  "#px-timeout", "#px-threads", "#sm-timeout", "#sm-threads",
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
// «Убрать не пров.» — удаляет ТОЛЬКО непроверенные (отдельно от «Убрать мёртвые»).
$("#px-remove-untested").addEventListener("click", () => api().remove_untested_proxies().then(() => { pagers.proxies.reload(); refreshBadges(); }));
$("#sm-remove-untested").addEventListener("click", () => api().remove_untested_smtp().then(() => { pagers.smtp.reload(); refreshBadges(); }));

function setPct(p, pct) {
  $("#" + p + "-progress").style.width = pct + "%";
  $("#" + p + "-progress-pct").textContent = pct + "%";
}
// Единый источник правды для бара: считаем непроверенных (untested = всего−живых−мёртвых) и
// решаем и видимость, и процент. Ключевое правило владельца: 100% — ТОЛЬКО когда непроверенных 0.
function updateProgress(p, r) {
  const total = r.total || 0, alive = r.alive || 0, dead = r.dead || 0;
  const untested = Math.max(0, total - alive - dead);
  const running = !!r.running, done = r.done || 0;
  const wrap = $("#" + p + "-progress-wrap");
  // Бар виден, когда есть данные И (идёт проверка ИЛИ хоть что-то уже проверено). Он ОСТАЁТСЯ
  // после завершения (untested < total → показан). Свежезагруженный непроверенный пул
  // (untested == total, проверка не идёт) и пустой пул (total 0) — бар скрыт.
  const show = total > 0 && (running || untested < total);
  wrap.hidden = !show;
  if (!show) { setPct(p, 0); return; }
  let pct;
  if (untested === 0) {
    pct = 100;  // 100% ТОЛЬКО когда непроверенных реально не осталось
  } else {
    // Пока идёт проверка — плавно по done/цель (real-time); после — по доле проверенных.
    // Цель — check_total (при «Перепроверить не пров.» это число непроверенных, а не весь
    // пул), иначе весь пул. Пока есть хоть один непроверенный — потолок 99%.
    const chkTotal = r.check_total || total;
    const base = running ? (chkTotal ? done / chkTotal : 0) : (total - untested) / total;
    pct = Math.min(99, Math.max(0, Math.floor(base * 100)));
  }
  setPct(p, pct);
}
function runCheck(kind, onlyUntested) {
  const p = kind === "proxies" ? "px" : "sm";
  // Значения ползунков: таймаут (сек) и число потоков — передаём в проверку.
  const threads = +$("#" + p + "-threads").value;
  const timeout = +$("#" + p + "-timeout").value;
  // onlyUntested=true → «Перепроверить не пров.»: сервер перегонит только «?».
  api()["check_" + kind](threads, timeout, !!onlyUntested).then((r) => {
    if (r.busy || r.empty) return;
    setBusy(true);   // лок настроек/загрузки/старта (пагинация НЕ блокируется)
    pollCheck(kind); // первый poll покажет бар и процент через updateProgress
  });
}
function pollCheck(kind) {
  const p = kind === "proxies" ? "px" : "sm";
  // refresh() перерисовывает ТЕКУЩУЮ страницу (её статусы и счётчики меняются по мере
  // проверки) → renderList → updateProgress сам двигает бар. Здесь только цикл опроса.
  pagers[kind].refresh().then((st) => {
    if (st.running) setTimeout(() => pollCheck(kind), 700);
    else {
      // Проверка завершена. Кэш счётчиков уже сброшен на сервере (on_done), поэтому
      // setBusy(false) → refresh даст ТОЧНЫЕ счётчики (непроверенных 0) → бар станет 100%
      // и ОСТАНЕТСЯ. Ничего не прячем и не форсим 100 вручную — только правда из данных.
      setBusy(false);
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

// ── Пресеты кампании (сохранение/список/загрузка настроек) ───────────────
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
// Конфиг реального интерфейса каждого клиента: бренд-цвет, логотип, поиск, папки сайдбара
// (на языке клиента), подпись «кому», кнопки действий. По ним clientHTML() строит узнаваемый
// хром — как на charly.cash/letter-preview, а не одна рамка на всех.
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
// Смена клиента/устройства/темы/картинок — полная перерисовка хрома клиента.
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
    $("#pv-format").textContent = d.format;
    const m = d.metrics || {};
    $("#pv-m-html").textContent = m.html_size || 0; $("#pv-m-text").textContent = m.text_len || 0;
    $("#pv-m-links").textContent = m.links || 0; $("#pv-m-img").textContent = m.images || 0;
    // Баннер: показанный шаблон (тема/тело) уйдёт получателю битым — честное предупреждение.
    const iss = (d.subject_issue || []).concat(d.body_issue || []);
    const w = $("#pv-warn");
    if (w) {
      if (iss.length) { w.hidden = false; w.textContent = "⚠ Показанный шаблон УЙДЁТ ПОЛУЧАТЕЛЮ БИТЫМ (ошибка спинтакса: " + iss.join(", ") + "). Именно так письмо и придёт — сырой «{ … | … }». Почини шаблон в контенте."; }
      else { w.hidden = true; }
    }
    $("#pv-loading").style.display = "none"; $("#pv-client-frame").style.display = "block";
    renderPreview();
  });
}
// Строит РЕАЛИСТИЧНЫЙ хром выбранного клиента вокруг песочницы-iframe с телом письма.
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
  // Подгоняем высоту iframe под содержимое письма (в тех же рамках, что и раньше).
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

  // ── Мобильный: узкая колонка почтового приложения (шапка → письмо → нижний бар) ──
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

  // ── Apple Mail: мак-окно (светофор) + блок шапки From/Subject/To ──
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

  // ── Обычный веб-клиент: топбар (лого+поиск) → сайдбар папок → чтение письма ──
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
  const pxBL = (i) => i % 7 === 0;  // в блоклисте (DNSBL) — теперь это МЕТКА, а не приговор
  // DNSBL — метка, а не смерть: живой-в-блоклисте ОСТАЁТСЯ живым (в UI помечен ⚑BL).
  const pxStatus = (i) => (pxFinal(i) === "dead") ? "dead" : "alive";
  // Причина смерти для демо: часть мёртвых «подключились быстро, но почтовик не поздоровался»
  // (пинг есть + бан IP) — ровно случай владельца «171 ms + Мёртвый»; остальные — прокси не отвечает.
  const pxErr = (i) => pxStatus(i) !== "dead" ? ""
    : (i % 8 === 1 ? "smtp.gmail.com:587 не прислал '220' — IP прокси, вероятно, в бане у почтовика"
      : "прокси не отвечает: SOCKS-подключение отклонено (порт закрыт или прокси мёртв)");
  let proxies = Array.from({ length: N_PX }, (_, i) => ({ addr: `104.28.${(i % 250)}.${(i % 99) + 1}:1080`, proto: "socks5", status: pxStatus(i), ping: pxStatus(i) === "alive" ? 150 + (i % 200) : (i % 8 === 1 ? 171 : 0), country: pxStatus(i) === "alive" ? "DE" : "", blacklist: pxBL(i) ? false : true, score: pxStatus(i) === "alive" ? 80 : 0, error: pxErr(i) }));
  // proxy — через какой прокси аккаунт проверялся (демо): часть через пул, часть напрямую.
  const smProxy = (i) => (i % 6 === 3 ? "прямое соединение" : `185.${20 + (i % 60)}.${i % 250}.${(i % 99) + 1}:1080`);
  let smtps = Array.from({ length: N_SM }, (_, i) => ({ host: `smtp.mail${i}.com:587`, email: `sender${i + 1}@mail${i % 40}.com`, enc: "STARTTLS", status: smFinal(i), ping: smFinal(i) === "alive" ? 200 + (i % 120) : 0, error: smErr(i), bound_proxy: false, proxy: smProxy(i) }));
  let pxChecked = false, smChecked = false;  // «Проверить все» переводит в true (после завершения)
  let pxRun = false, smRun = false;  // окно «идёт проверка» (для наблюдаемого лока UI)
  let pxDone = 0, smDone = 0;  // сколько уже «проверено» в демо — растёт с каждым опросом
  // clean/dirty — только для прокси (у SMTP поля blacklist нет, dirty=0). Чистый = живой и не в блэклисте.
  const cnt = (arr) => ({ total: arr.length, alive: arr.filter((x) => x.status === "alive").length, dead: arr.filter((x) => x.status === "dead").length, clean: arr.filter((x) => x.status === "alive" && x.blacklist !== false).length, dirty: arr.filter((x) => x.status === "alive" && x.blacklist === false).length });
  // До проверки пул виден как «не пров.» (untested), после — с реальными статусами.
  const viewItems = (arr, ok) => ok ? arr : arr.map((x) => ({ ...x, status: "untested", ping: 0, country: "", error: "", blacklist: null, proxy: "" }));
  const viewCnt = (arr, ok) => ok ? cnt(arr) : { total: arr.length, alive: 0, dead: 0, clean: 0, dirty: 0 };
  // Инкрементальная проверка для демо: первые n элементов «проверены», остальные — untested.
  // Это даёт настоящую динамику бара (непроверенных n→0) и показ 100% строго при 0 непровер.
  const cntN = (arr, n) => { const d = arr.slice(0, n); return { total: arr.length, alive: d.filter((x) => x.status === "alive").length, dead: d.filter((x) => x.status === "dead").length, clean: d.filter((x) => x.status === "alive" && x.blacklist !== false).length, dirty: d.filter((x) => x.status === "alive" && x.blacklist === false).length }; };
  const itemsN = (arr, n) => arr.map((x, i) => i < n ? x : ({ ...x, status: "untested", ping: 0, country: "", error: "", blacklist: null, proxy: "" }));
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
    page_proxies: (o, l) => {
      // Каждый опрос во время проверки продвигает «проверено» на ~1/6 пула (за ~6 опросов до конца).
      if (pxRun) { pxDone = Math.min(proxies.length, pxDone + Math.max(1, Math.ceil(proxies.length / 6))); if (pxDone >= proxies.length) { pxRun = false; pxChecked = true; } }
      const n = pxChecked ? proxies.length : (pxRun ? pxDone : 0);
      const w = win(itemsN(proxies, n), o, l);
      return P({ ...cntN(proxies, n), offset: w.off, limit: w.lim, items: w.arr, running: pxRun, done: n, check_total: proxies.length });
    },
    page_smtp: (o, l) => {
      if (smRun) { smDone = Math.min(smtps.length, smDone + Math.max(1, Math.ceil(smtps.length / 6))); if (smDone >= smtps.length) { smRun = false; smChecked = true; } }
      const n = smChecked ? smtps.length : (smRun ? smDone : 0);
      const w = win(itemsN(smtps, n), o, l);
      return P({ ...cntN(smtps, n), offset: w.off, limit: w.lim, items: w.arr, running: smRun, done: n, check_total: smtps.length });
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
    remove_dead_smtp: () => { smtps = smtps.filter((x) => x.status !== "dead"); return P({ removed: 0, ...viewCnt(smtps, smChecked) }); },
    // Удаление непроверенных: в демо после полной проверки «untested» = первые статусы; для
    // наглядности убираем элементы с итоговым статусом untested (SMTP их даёт ~20%).
    remove_untested_proxies: () => { proxies = proxies.filter((x) => x.status !== "untested"); return P({ removed: 0, ...viewCnt(proxies, pxChecked) }); },
    remove_untested_smtp: () => { smtps = smtps.filter((x) => x.status !== "untested"); return P({ removed: 0, ...viewCnt(smtps, smChecked) }); },
    // Третий арг only_untested — в демо перепроверка проигрывается как обычная (логика
    // «только непроверенные» проверяется на реальном host.py в verify_web).
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
    preview_email: () => P({ from_name: "Мария Соколова", from_email: "sender1@mail1.com", subject: "Анна, у нас для тебя кое-что есть", preheader: "Загляни, пока предложение действует", html: demoBody, is_html: true, format: "HTML", metrics: { html_size: 980, text_len: 120, links: 1, images: 0 }, bodies: 7, subjects: N_SUBJ, subject_issue: [], body_issue: [] }),
    // Демо: показываем предупреждение о битом теле #3, чтобы жёлтая строка на карточке была видна.
    content_issues: () => P({ subjects: [], bodies: [{ n: 3, why: "незакрытая { ×1 (демо)" }] }),
    plan: () => P({ alive: 2, total: N_REC, rows: [{ email: "sender1@mail1.com", count: N_REC / 2 }, { email: "sender2@mail2.com", count: N_REC / 2 }], text: `2 отправителя разошлют ровно по ${N_REC / 2} писем.`, threads: 2, per_conn: N_REC / 2 }),
    send_test: () => P({ ok: true, info: "отправлено за 1.8 сек через sender1@mail1.com" }),
    queue_state: () => P({ exists: false }),
    campaign_state: () => P({ snapshot: { status_text: "Ожидание", sent: 0, errors: 0, total: 0, remaining: 0, running: false, paused: false, started_at: "—", speed_per_min: 0, eta_min: 0, progress: 0, smtp: [], proxy: [] }, log: [], running: false, paused: false, recipients: N_REC, alive_smtp: cnt(smtps).alive, can_start: true }),
  };
  window.pywebview = { api: mock };
  onReady();
}
