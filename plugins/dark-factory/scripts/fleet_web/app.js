// The factory on the phone as a web page: the menu bar app's feed and rules (macos/FactoryBar) on iOS-style screens,
// live over /events while open. No framework: the page is small and the server ships it as is.
"use strict";

const STALE_AFTER = 2700e3;   // the server's 15-minute update older than this is "no data"
const LOST_AFTER = 10e3;      // no connection for this long is "no data"
const BACKOFF = [1, 2, 5, 10, 30];
const TOKEN_KEY = "factory-token";

const S = { feed: null, everReceived: false, connected: false, lostAt: Date.now(), auth: null, legacy: false };

// ---------- token ----------

function token() { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } }
function setToken(t) { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch {} }

// A link with #token=… sets it once (the fragment never reaches the server) and is cleaned from the address bar.
(function tokenFromLink() {
  const m = location.hash.match(/token=([^&]+)/);
  if (!m) return;
  setToken(decodeURIComponent(m[1]));
  history.replaceState(null, "", location.pathname);
})();

function headers() { const t = token(); return t ? { Authorization: `Bearer ${t}` } : {}; }

// ---------- connection ----------

let attempt = 0, controller = null;

async function connect() {
  controller?.abort();
  controller = new AbortController();
  try {
    const r = await fetch("events", { headers: headers(), signal: controller.signal, cache: "no-store" });
    if (r.status === 401) return unauthorized();
    if (r.status === 404) return legacyPoll();          // an older server: status.json once a minute
    if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
    S.connected = true; S.lostAt = null; S.auth = null; attempt = 0; render();
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "", data = [];
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).replace(/\r$/, ""); buf = buf.slice(i + 1);
        if (line === "") { if (data.length) receive(data.join("\n")); data = []; }
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
    }
    throw new Error("stream closed");
  } catch (e) {
    if (e.name === "AbortError") return;
    lost();
    setTimeout(connect, BACKOFF[Math.min(attempt++, BACKOFF.length - 1)] * 1000);
  }
}

async function legacyPoll() {
  S.legacy = true;
  try {
    const r = await fetch("status.json", { headers: headers(), cache: "no-store" });
    if (r.status === 401) return unauthorized();
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    S.connected = true; S.lostAt = null; S.auth = null;
    receive(await r.text());
  } catch { lost(); }
  setTimeout(legacyPoll, 60e3);
}

function receive(text) {
  try { S.feed = JSON.parse(text); S.everReceived = true; } catch { return; }
  render();
}

function lost() {
  S.connected = false;
  if (S.lostAt == null) S.lostAt = Date.now();
  render();
}

function unauthorized() {
  S.connected = false; S.auth = token() ? "rejected" : "missing";
  if (S.lostAt == null) S.lostAt = Date.now();
  render();
  if (!document.getElementById("settings").open) openSettings();
}

// ---------- state (the rules of Shared/FeedState.swift) ----------

const t = (iso) => (iso ? Date.parse(iso) : null);
const heavyAt = (f) => t(f.full_at) ?? t(f.generated_at);
const isWorkingNow = (p) => p.working || p.waiting_quota;

function state(now = Date.now()) {
  if (S.auth) return { kind: "nodata", reason: S.auth === "rejected" ? "Feed token rejected" : "Feed token missing" };
  if (S.lostAt != null && now - S.lostAt >= LOST_AFTER)
    return { kind: "nodata", reason: S.everReceived ? "Connection lost" : "Server unreachable", lastGood: S.feed && heavyAt(S.feed) };
  const f = S.feed;
  if (!f) return { kind: "connecting" };
  if (now - heavyAt(f) > STALE_AFTER)
    return { kind: "nodata", reason: `Status not updated since ${clock(heavyAt(f))}`, lastGood: heavyAt(f) };
  if (f.projects.some((p) => p.working)) return { kind: "working", agents: f.projects.reduce((n, p) => n + p.agents, 0) };
  return { kind: f.projects.some((p) => p.waiting_quota) ? "waiting" : "idle" };
}

const STATE_COLOR = { working: "var(--ok)", waiting: "var(--warn)", idle: "var(--idle)", nodata: "var(--bad)", connecting: "var(--idle)" };
const STATE_TITLE = { working: "Working", waiting: "Waiting for quota", idle: "Idle", nodata: "No data", connecting: "Connecting…" };

function rowStatus(p, quota) {
  if (p.working) return { kind: "building", sessions: p.busy_sessions, agents: p.agents };
  if (p.waiting_quota) return { kind: "waiting", until: t(quota?.resets_at), queued: p.queue_ready };
  return { kind: "last", when: t(p.last_worked_at) };
}

function counts(sessions, agents) {
  const out = [];
  if (sessions > 0) out.push(`${sessions} session${sessions === 1 ? "" : "s"}`);
  if (agents > 0) out.push(`${agents} agent${agents === 1 ? "" : "s"}`);
  return out;
}

function statusText(s, now) {
  if (s.kind === "building") return ["Building", ...counts(s.sessions, s.agents)].join(" · ");
  if (s.kind === "waiting") return `Waiting for quota${s.until ? ` until ${clock(s.until)}` : ""} · ${s.queued} queued`;
  return s.when ? `Last worked ${dayAndTime(s.when, now)}` : "Not worked yet";
}

function heroSubtitle(st, f, now) {
  if (st.kind === "nodata") return st.reason;
  if (!f) return "";
  const n = f.projects.length, inFactory = `${n} project${n === 1 ? "" : "s"}`;
  if (st.kind === "working") {
    const working = f.projects.filter((p) => p.working).length;
    const sessions = f.projects.reduce((s, p) => s + (p.busy_sessions || 0), 0);
    return [`${working} of ${inFactory} building`, sessions ? `${sessions} session${sessions === 1 ? "" : "s"}` : null]
      .filter(Boolean).join(" · ");
  }
  if (st.kind === "waiting") {
    const queued = f.projects.filter((p) => p.waiting_quota).reduce((s, p) => s + p.queue_ready, 0);
    const back = untilText(t(f.quota?.resets?.five_hour), now);
    return [`${queued} task${queued === 1 ? "" : "s"} queued`, back && `quota back in ${back}`].filter(Boolean).join(" · ");
  }
  const last = Math.max(...f.projects.map((p) => t(p.last_worked_at) || 0));
  return [inFactory, last ? `last work ${dayAndTime(last, now)}` : null].filter(Boolean).join(" · ");
}

const JOB_LABELS = { janitor: "Janitor", analytics: "Analytics", watch: "Watcher", feed: "Feed", routines: "Cloud check",
                     stand: "Stand", "desk-watch": "On-call guard" };
const jobLabel = (j) => JOB_LABELS[j.name] || j.title || j.name;
const notRunning = (j) => j.installed === false || j.enabled === false;
function jobProblem(j) {
  if (j.installed === false) return "not installed";
  if (j.enabled === false) return "off";
  if (j.result === "failed") return "failed";
  if (j.result === "running") return "running";
  return null;
}
function whenText(schedule, nextAt, now) {
  if (schedule && schedule.startsWith("every ")) return schedule;
  if (!nextAt) return null;
  const next = new Date(nextAt), today = new Date(now), tomorrow = new Date(now + 864e5);
  if (sameDay(next, today)) return `next ${clock(nextAt)}`;
  if (sameDay(next, tomorrow)) return `next tomorrow ${clock(nextAt)}`;
  return `next ${dayAndTime(nextAt, now)}`;
}

/** What a person should look at: broken projects, stopped services, failed timers. */
function issues(f) {
  const out = [];
  for (const p of f.projects) {
    if (p.error) out.push({ title: p.name, detail: p.error, icon: "⚠︎", tint: "var(--warn)", project: p.name });
    if (p.watchdog?.installed && !p.watchdog.ok && !p.error)
      out.push({ title: p.name, detail: "Watchdog is off", icon: "⛉", tint: "var(--warn)", project: p.name });
    if (p.oncall?.installed && !p.oncall.running)
      out.push({ title: p.name, detail: "On-call is not running", icon: "☎︎", tint: "var(--warn)", project: p.name });
  }
  const jobs = (f.scheduled?.server || []).filter((j) => j.result === "failed" || notRunning(j));
  const routines = (f.scheduled?.cloud?.routines || []).filter((r) => r.enabled && r.result === "failed");
  const names = [...jobs.map(jobLabel), ...routines.map((r) => r.name)];
  if (names.length)
    out.push({ title: "Scheduled work", detail: `${names.join(", ")} ${names.length === 1 ? "needs" : "need"} a look`,
               icon: "◷", tint: "var(--bad)", project: null });
  return out;
}

function standFreshness(s) {
  if (!s.ref) return null;
  const behind = s.behind || 0, ahead = s.ahead || 0;
  if (s.ref === "main" && !ahead) return behind ? `${behind} behind main` : "on main";
  return [s.ref, ahead ? `+${ahead} to main` : null, behind ? `${behind} behind` : null].filter(Boolean).join(" · ");
}

function versionText(v) {
  if (!v?.version) return null;
  if (!v.latest || v.latest === v.version) return { text: v.version, behind: false };
  return { text: `${v.version} → ${v.latest}`, behind: true };
}

/** Only Claude's own https links open from the page, as in the apps. */
function claudeLink(u) {
  try { const x = new URL(u); return x.protocol === "https:" && x.host === "claude.ai" ? x.href : null; } catch { return null; }
}
function standLink(u) {
  try { const x = new URL(u); return x.protocol === "https:" ? x.href : null; } catch { return null; }
}

// ---------- time ----------

const pad = (n) => String(n).padStart(2, "0");
const clock = (ms) => { const d = new Date(ms); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dayAndTime(ms, now) {
  const d = new Date(ms);
  if (sameDay(d, new Date(now))) return `today ${clock(ms)}`;
  if (sameDay(d, new Date(now - 864e5))) return `yesterday ${clock(ms)}`;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${clock(ms)}`;
}
function untilText(ms, now) {
  if (!ms) return null;
  const m = Math.floor((ms - now) / 60e3);
  if (m <= 0) return null;
  if (m < 60) return `${m}m`;
  if (m < 1440) return m % 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m / 60}h`;
  const h = Math.floor(m / 60);
  return h % 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h / 24}d`;
}

// ---------- drawing ----------

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** The factory glyph of the apps (Shared/Glyphs.swift), filled while working or waiting, outlined otherwise. */
function glyph(filled) {
  return filled
    ? `<svg class="glyph" viewBox="0 0 24 24"><path d="M2 21V10l5 3v-3l5 3v-3l5 3V4h4v17z" fill="currentColor"/></svg>`
    : `<svg class="glyph" viewBox="0 0 24 24"><path d="M2.9 20.1v-8.5l5 3v-3l5 3v-3l5 3V4.9h2.2v15.2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`;
}
const CHEV = `<svg class="chev" viewBox="0 0 8 14"><path d="M1 1l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICONS = {
  hammer: `<svg viewBox="0 0 24 24"><path d="M14.5 3.5 20 9l-2.5 2.5-1.8-1.8L6 19.4a1.8 1.8 0 0 1-2.5-2.5l9.7-9.7-1.8-1.8z" fill="currentColor"/></svg>`,
  hourglass: `<svg viewBox="0 0 24 24"><path d="M6 3h12M6 21h12M7 3c0 5 5 6 5 9s-5 4-5 9M17 3c0 5-5 6-5 9s5 4 5 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
  moon: `<svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" fill="currentColor"/></svg>`,
};
function badge(s, large = false) {
  const kind = s.kind === "building" ? "building" : s.kind === "waiting" ? "waiting" : "";
  const icon = s.kind === "building" ? ICONS.hammer : s.kind === "waiting" ? ICONS.hourglass : ICONS.moon;
  return `<div class="badge ${kind} ${large ? "large" : ""}">${icon}</div>`;
}
function ring(label, value, resets, now) {
  const v = Math.min(Math.max(value, 0), 100), color = v >= 80 ? "var(--warn)" : "var(--accent)";
  const c = 2 * Math.PI * 20, left = untilText(t(resets), now);
  return `<div><div class="ring"><svg viewBox="0 0 46 46"><circle cx="23" cy="23" r="20" fill="none" stroke="${color}" stroke-opacity=".15" stroke-width="6"/>
    <circle cx="23" cy="23" r="20" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${(c * v) / 100} ${c}"/></svg>
    <b>${Math.round(value)}</b></div><div><div class="name">${label}</div><div class="left">${left ? `${left} left` : `${Math.round(value)}% used`}</div></div></div>`;
}
const section = (title, body, foot = "") =>
  `<section class="section">${title ? `<h2>${esc(title)}</h2>` : ""}<div class="group">${body}</div>${foot ? `<p class="foot">${foot}</p>` : ""}</section>`;
function fact(icon, tint, title, value, href) {
  const inner = `<div class="icon" style="color:${tint}">${icon}</div><div class="text title">${esc(title)}</div>
    ${value ? `<div class="value">${esc(value)}</div>` : ""}${href ? `<span class="ext">↗</span>` : ""}`;
  return href ? `<a class="row" href="${esc(href)}" target="_blank" rel="noopener">${inner}</a>` : `<div class="row">${inner}</div>`;
}

function hero(st, f, now) {
  const v = versionText(f?.factory);
  const pill = S.auth ? `<span class="pill bad">Token ${S.auth}</span>`
    : S.connected ? `<span class="pill live"><i></i>Live</span>`
    : `<span class="pill off"><i></i>${S.everReceived ? "Reconnecting" : "Connecting"}</span>`;
  const big = st.kind === "working" && st.agents > 0
    ? `<div class="big"><span class="count">${st.agents}</span><span class="unit"><b>${st.agents === 1 ? "agent" : "agents"}</b><span>Working</span></span></div>`
    : `<div class="word ${st.kind}">${STATE_TITLE[st.kind]}</div>`;
  const sub = heroSubtitle(st, f, now);
  return `<div class="hero"><div class="top">${glyph(st.kind === "working" || st.kind === "waiting")}
    ${v ? `<span class="pill version ${v.behind ? "behind" : ""}">${esc(v.text)}</span>` : ""}<span class="spacer"></span>${pill}</div>
    ${big}${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>`;
}

function projectRow(p, f, now) {
  const s = rowStatus(p, f.quota);
  const behind = p.template?.current === false && p.template.version ? `<span class="tag">template ${esc(p.template.version)}</span>` : "";
  return `<a class="row" href="#/p/${encodeURIComponent(p.name)}">${badge(s)}<div class="text">
    <div class="title">${esc(p.name)}${behind}</div><div class="detail">${esc(statusText(s, now))}</div>
    ${p.error ? `<div class="error">⚠︎ ${esc(p.error)}</div>` : ""}</div>${CHEV}</a>`;
}

function overview(now) {
  const st = state(now), f = S.feed;
  let html = hero(st, f, now);
  if (st.kind === "nodata" && !f) return html;
  if (!f) return html;
  const list = issues(f);
  if (list.length)
    html += section("Needs attention", list.map((i) =>
      `<a class="row" href="${i.project ? `#/p/${encodeURIComponent(i.project)}` : "#/scheduled"}">
        <div class="icon" style="color:${i.tint}">${i.icon}</div><div class="text"><div class="title">${esc(i.title)}</div>
        <div class="detail">${esc(i.detail)}</div></div>${CHEV}</a>`).join(""));
  html += section("Quota", f.quota
    ? `<div class="quota plain-row">${ring("5-hour", f.quota.five_hour, f.quota.resets?.five_hour, now)}${ring("7-day", f.quota.seven_day, f.quota.resets?.seven_day, now)}</div>`
    : `<div class="row plain-row"><div class="text detail">Quota unknown</div></div>`);
  const active = f.projects.filter(isWorkingNow), idle = f.projects.filter((p) => !isWorkingNow(p));
  if (active.length) html += section("Working now", active.map((p) => projectRow(p, f, now)).join(""));
  if (idle.length) html += section(active.length ? "Idle" : "Projects", idle.map((p) => projectRow(p, f, now)).join(""));
  if (!f.projects.length) html += section("", `<div class="row plain-row"><div class="text detail">No projects in the feed</div></div>`);
  html += section("", `<a class="row" href="#/scheduled"><div class="icon" style="color:var(--accent)">◷</div>
      <div class="text title">Scheduled work</div>${issues(f).some((i) => !i.project) ? `<span style="color:var(--warn)">⚠︎</span>` : ""}${CHEV}</a>`,
    `<span class="center" style="display:block">Updated ${clock(heavyAt(f))} · next at ${clock(heavyAt(f) + 900e3)}</span>`);
  return html;
}

function project(name, now) {
  const f = S.feed, p = f?.projects.find((x) => x.name === name);
  if (!p) return `<p class="empty">${esc(name)}<br>${f ? "Not in the feed." : "Waiting for the feed."}</p>`;
  const s = rowStatus(p, f.quota);
  let html = `<div class="head">${badge(s, true)}<h2>${esc(p.name)}</h2><p>${esc(statusText(s, now))}</p>
    ${p.template?.current === false && p.template.version ? `<p style="color:var(--warn)">template ${esc(p.template.version)}</p>` : ""}</div>`;
  if (p.error) html += section("", `<div class="row plain-row" style="color:var(--warn)">⚠︎ ${esc(p.error)}</div>`);
  const session = claudeLink(p.session_url);
  if (session) html += section("", `<a class="row plain-row action" href="${esc(session)}" target="_blank" rel="noopener">Open session in Claude</a>`);
  if (p.stands?.length)
    html += section("Stands", p.stands.map((x) => fact("▣", x.state === "running" ? "var(--ok)" : "var(--muted)", x.name,
      [x.state, standFreshness(x)].filter(Boolean).join(" · "), x.state === "running" ? standLink(x.url) : null)).join(""));
  let services = "";
  if (p.oncall?.installed)
    services += fact("☎︎", p.oncall.running ? "var(--ok)" : "var(--muted)", "On-call",
      [p.oncall.running ? "running" : "not running", p.oncall.last_message_at ? `wrote ${dayAndTime(t(p.oncall.last_message_at), now)}` : null]
        .filter(Boolean).join(" · "), claudeLink(p.oncall.session_url));
  if (p.watchdog?.installed) services += fact("⛉", p.watchdog.ok ? "var(--ok)" : "var(--warn)", "Watchdog", p.watchdog.ok ? "on" : "off");
  services += fact("▤", p.queue_ready > 0 ? "var(--accent)" : "var(--muted)", "Queue", p.queue_ready > 0 ? `${p.queue_ready} ready` : "empty");
  html += section("Services", services);
  if (p.level) {
    let lv = fact("⌗", "var(--accent)", `Level ${p.level.level}`, p.level.name);
    if (p.level.fence) lv += fact("⬚", "var(--muted)", "Fence", p.level.fence);
    if (p.level.next) lv += fact("↗", "var(--muted)", "Next", p.level.next);
    if (p.level.modules?.length) {
      const n = p.level.modules.filter((m) => m.installed).length;
      lv += `<details class="mods"><summary class="row"><div class="icon" style="color:var(--muted)">◫</div><div class="text title">Modules</div>
        <div class="value">${n} of ${p.level.modules.length} installed</div></summary>
        ${p.level.modules.map((m) => fact(m.installed ? "✓" : "○", m.installed ? "var(--ok)" : "var(--muted)", m.name, m.installed ? "installed" : "")).join("")}</details>`;
    }
    html += section("Level", lv);
  }
  if (p.scheduled?.length) html += section("Timers", p.scheduled.map((j) => jobRow(j, now)).join(""));
  return html;
}

function jobRow(j, now) {
  const [icon, tint] = notRunning(j) ? ["⚠︎", "var(--warn)"] : j.result === "failed" ? ["✕", "var(--bad)"]
    : j.result === "running" ? ["↻", "var(--accent)"] : j.result === "ok" ? ["✓", "var(--ok)"] : ["◷", "var(--muted)"];
  return fact(icon, tint, jobLabel(j), [whenText(j.schedule, t(j.next_at), now), jobProblem(j)].filter(Boolean).join(" · "));
}

function scheduledView(now) {
  const f = S.feed;
  if (!f) return `<p class="empty">Waiting for the feed.</p>`;
  let html = "";
  const v = versionText(f.factory);
  if (v) html += section("", fact("⬢", v.behind ? "var(--warn)" : "var(--accent)", "Factory release", v.text),
    v.behind ? "A newer canon release is out." : "");
  const server = f.scheduled?.server;
  html += section("Server", server ? server.map((j) => jobRow(j, now)).join("")
    : `<div class="row plain-row"><div class="text detail">Unknown on this server</div></div>`);
  const cloud = f.scheduled?.cloud;
  html += section("Cloud routines", cloud ? cloud.routines.map((r) => fact("☁︎",
      !r.enabled ? "var(--muted)" : r.result === "failed" ? "var(--bad)" : "var(--accent)", r.name,
      [whenText(null, t(r.next_at), now), r.enabled ? (r.result === "ok" ? null : r.result) : "off"].filter(Boolean).join(" · "),
      claudeLink(r.session_url))).join("")
    : `<div class="row plain-row"><div class="text detail">Not checked yet</div></div>`,
    cloud?.checked_at ? `Checked ${dayAndTime(t(cloud.checked_at), now)}` : "");
  return html;
}

function render() {
  const now = Date.now(), st = state(now), route = location.hash;
  document.documentElement.style.setProperty("--state", STATE_COLOR[st.kind]);
  const bar = document.querySelector(".bar"), title = document.getElementById("title"), back = document.getElementById("back");
  const open = document.querySelector("details.mods")?.open;
  let html;
  if (route.startsWith("#/p/")) {
    const name = decodeURIComponent(route.slice(4));
    title.textContent = name; html = project(name, now);
  } else if (route === "#/scheduled") {
    title.textContent = "Scheduled work"; html = scheduledView(now);
  } else {
    title.textContent = "Factory"; html = overview(now);
  }
  const inner = route.startsWith("#/");
  bar.classList.toggle("inner", inner); back.hidden = !inner;
  document.getElementById("view").innerHTML = html;
  if (open) document.querySelector("details.mods")?.setAttribute("open", "");
}

// ---------- settings ----------

function openSettings() {
  document.getElementById("token").value = token();
  document.getElementById("settings").showModal();
}
document.getElementById("gear").addEventListener("click", openSettings);
document.getElementById("settings").addEventListener("close", (e) => {
  if (e.target.returnValue !== "save") return;
  setToken(document.getElementById("token").value.trim());
  S.auth = null; S.feed = null; S.everReceived = false; S.lostAt = Date.now(); attempt = 0;
  render();
  S.legacy ? legacyPoll() : connect();
});
document.getElementById("back").addEventListener("click", () => {
  if (history.length > 1) history.back(); else location.hash = "";
});

// ---------- start ----------

window.addEventListener("hashchange", () => { render(); scrollTo(0, 0); });
setInterval(render, 30e3);  // the times on screen, and "no data" once the feed turns stale or the line stays down
document.addEventListener("visibilitychange", () => { if (!document.hidden && !S.connected) { attempt = 0; connect(); } });
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
render();
connect();
