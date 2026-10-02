"""
STAGE 7 -- THE WEB PAGES (frontend), delivered as ONE Python file
Running this file (or starting stage6_api.py, which calls it) creates the folder  frontend/  next to it:

    frontend/index.html      the page structure (login, dashboard, network + spread animation, communities, users, spread experiments, join)
    frontend/style.css       colours and layout
    frontend/app.js          the behaviour: fetch() calls to the API (Stage 8), D3 network drawing, forms
    frontend/vendor/d3.min.js   the D3 library (v7, ISC licence), stored compressed below so the site works offline

You can open those files afterwards and edit them; if you change the text in THIS file, delete the frontend folder or
raise VERSION so the folder is rebuilt.

Run:  /usr/local/bin/python3 stage7_frontend.py
"""
import base64
import zlib
from pathlib import Path

VERSION = "4-spread"

INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Social Network Community Explorer</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<!-- ========== LOGIN (demo gate) ========== -->
<section id="login" class="login hidden">
  <form id="loginForm" class="login-card" autocomplete="off">
    <h1>Community Explorer</h1>
    <p class="muted">Interactive social media community and information-flow visualisation</p>
    <label>Username <input id="user" value="demo" required></label>
    <label>Password <input id="pass" type="password" value="graph123" required></label>
    <button type="submit">Sign in</button>
    <p id="loginErr" class="err"></p>
    <p class="muted small">Demo sign-in for the presentation (username <b>demo</b>, password <b>graph123</b>). It is not real security: the check happens in the browser.</p>
  </form>
</section>

<!-- ========== APP ========== -->
<div id="app" class="hidden">
  <header>
    <div class="brand">Community Explorer</div>
    <nav id="tabs">
      <a href="#dashboard" data-tab="dashboard">Dashboard</a>
      <a href="#network" data-tab="network">Network</a>
      <a href="#communities" data-tab="communities">Communities</a>
      <a href="#users" data-tab="users">Users</a>
      <a href="#spread" data-tab="spread">Spread</a>
      <a href="#join" data-tab="join">Join</a>
    </nav>
    <div class="who"><span id="whoName"></span> <button id="logout" class="link">Sign out</button></div>
  </header>

  <main>
    <!-- DASHBOARD -->
    <section id="tab-dashboard" class="tab">
      <div id="kpis" class="kpis"></div>
      <div class="grid2">
        <div class="card"><h3>Community sizes</h3><div id="sizeBars"></div></div>
        <div class="card"><h3>Friendships between communities</h3><p class="muted small">Darker = more friendships. The diagonal is friendships inside a community.</p><div id="matrix"></div></div>
      </div>
      <div class="grid2">
        <div class="card"><h3>10 most connected users</h3><table id="topUsers"></table></div>
        <div class="card"><h3>Top hashtags <select id="tagCommunity"></select></h3><div id="tagBars"></div></div>
      </div>
    </section>

    <!-- NETWORK -->
    <section id="tab-network" class="tab">
      <div class="toolbar">
        <label>Community <select id="netCommunity"></select></label>
        <label>Min friends <input id="netMin" type="range" min="0" max="40" value="0"><output id="netMinOut">0</output></label>
        <label>Max users <input id="netLimit" type="range" min="50" max="1000" step="50" value="400"><output id="netLimitOut">400</output></label>
        <label>Colour by <select id="netColor"><option value="community">community</option><option value="account_type">account type</option></select></label>
        <label><input id="netGroup" type="checkbox" checked> group by community</label>
        <input id="netSearch" placeholder="find a user, press Enter" list="none">
        <span id="netInfo" class="muted small"></span>
      </div>
      <div class="toolbar" id="spreadBar">
        <b>Simulate a post:</b>
        <label>seeds <select id="spStrategy"><option value="top degree">the most connected users</option><option value="one per community">top user of each community</option>
          <option value="top bridges">bridge users</option><option value="random">random users</option><option value="selected">the user I clicked</option></select></label>
        <label>how many <input id="spK" type="range" min="1" max="10" value="5"><output id="spKOut">5</output></label>
        <label>chance a friend passes it on <input id="spP" type="range" min="0.02" max="0.4" step="0.01" value="0.12"><output id="spPOut">0.12</output></label>
        <button id="spGo">Start</button> <button id="spClear" class="link">Clear</button>
        <span id="spInfo" class="muted small"></span>
      </div>
      <div class="netwrap">
        <canvas id="net"></canvas>
        <div id="legend" class="legend"></div>
        <div id="tip" class="tip hidden"></div>
        <button id="fitBtn" class="fit">Fit to screen</button>
        <p class="hint">Scroll to zoom, drag background to pan, drag a node to move it, hover to highlight friends, click for details.</p>
      </div>
    </section>

    <!-- COMMUNITIES -->
    <section id="tab-communities" class="tab">
      <div id="commCards" class="cards"></div>
      <div id="commDetail" class="card hidden"></div>
    </section>

    <!-- USERS -->
    <section id="tab-users" class="tab">
      <div class="toolbar">
        <input id="uq" placeholder="search name or username">
        <label>Community <select id="uc"></select></label>
        <label>Interest <select id="ui"><option value="">all</option></select></label>
        <label>Sort <select id="us"><option value="degree">most friends</option><option value="name">name</option><option value="age">age</option><option value="joined">joined</option></select></label>
        <span id="uinfo" class="muted small"></span>
      </div>
      <div class="card"><table id="userTable"></table>
        <div class="pager"><button id="uprev">Previous</button><button id="unext">Next</button></div></div>
    </section>

    <!-- SPREAD: information flow experiments -->
    <section id="tab-spread" class="tab">
      <div class="card" style="margin-bottom:14px">
        <h3>How does a post travel through the network?</h3>
        <p class="muted">Model: <b>independent cascade</b>. A few seed users share a post. Every user who receives it gets <b>one chance</b> to pass it to each friend, and succeeds with probability <i>p</i>. It stops when nobody new is reached.</p>
        <div class="toolbar">
          <label>seeds (k) <input id="xK" type="range" min="1" max="20" value="5"><output id="xKOut">5</output></label>
          <label>probability p <input id="xP" type="range" min="0.02" max="0.4" step="0.01" value="0.12"><output id="xPOut">0.12</output></label>
          <button id="xGo">Run experiments</button> <button id="xAnim" class="link">Animate one on the network</button>
          <span id="xInfo" class="muted small"></span>
        </div>
      </div>
      <div class="grid2">
        <div class="card"><h3>A) Who should post first? <span class="muted small">(marketing)</span></h3><div id="xBars"></div><p id="xNoteA" class="muted small"></p></div>
        <div class="card"><h3>B) Block users to stop a rumour <span class="muted small">(fake news)</span></h3><div id="xLines"></div><p id="xNoteB" class="muted small"></p></div>
      </div>
    </section>

    <!-- JOIN: new user -> predicted community + people to follow -> saved in the database -->
    <section id="tab-join" class="tab">
      <div class="grid2">
        <form id="joinForm" class="card" autocomplete="off">
          <h3>Create a new account</h3>
          <div class="formgrid">
            <label>Full name <input id="jName" maxlength="60" required></label>
            <label>Username (optional) <input id="jUser" maxlength="30" placeholder="made from your name"><small id="jUserMsg" class="muted"></small></label>
            <label>Age <input id="jAge" type="number" min="13" max="100" value="22" required></label>
            <label>City <select id="jCity"></select></label>
            <label>Main interest <select id="jInterest"></select></label>
            <label>Account type <select id="jType"></select></label>
          </div>
          <h4>Hashtags you like <span class="muted small">(up to 5, optional)</span></h4>
          <div id="jTags"></div>
          <h4>People you already know <span class="muted small">(up to 10, optional)</span></h4>
          <input id="jFriendQ" placeholder="type a name or username to search">
          <div id="jFriendRes" class="results"></div>
          <div id="jFriends" class="chips"></div>
          <p><button type="submit">Predict my community</button> <span id="jErr" class="err"></span></p>
          <p class="muted small">Nothing is saved yet. First you see the prediction and recommendations, then you decide.</p>
        </form>
        <div id="joinResult" class="card hidden"></div>
      </div>
    </section>
  </main>

  <!-- PROFILE DRAWER (used by every tab) -->
  <aside id="drawer" class="drawer hidden">
    <button id="closeDrawer" class="link close">Close</button>
    <div id="drawerBody"></div>
  </aside>
</div>

<script src="/static/vendor/d3.min.js"></script>
<script src="/static/app.js"></script>
</body>
</html>
'''

STYLE_CSS = r''':root {
  --bg:#f5f6f8; --card:#fff; --ink:#1d2330; --muted:#697386; --line:#e3e6ec; --accent:#3b6fd4; --accent-ink:#fff; --bar:#dfe6f5;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#12151b; --card:#1b2029; --ink:#e7eaf0; --muted:#9aa3b2; --line:#2b3340; --accent:#6d9cf0; --accent-ink:#0d1117; --bar:#28324a; }
}
* { box-sizing:border-box; }
body { margin:0; font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif; background:var(--bg); color:var(--ink); }
.hidden { display:none !important; }
.muted { color:var(--muted); } .small { font-size:12px; } .err { color:#d64545; min-height:1.2em; }
button, select, input { font:inherit; color:inherit; }
button { background:var(--accent); color:var(--accent-ink); border:0; border-radius:6px; padding:7px 14px; cursor:pointer; }
button.link { background:none; color:var(--accent); padding:2px 6px; }
button:disabled { opacity:.4; cursor:default; }
select, input:not([type=range]):not([type=checkbox]) { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:6px 8px; }
a { color:var(--accent); }

/* login */
.login { min-height:100vh; display:grid; place-items:center; padding:16px; }
.login-card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:28px; width:min(380px,100%); display:grid; gap:12px; }
.login-card h1 { margin:0; font-size:22px; } .login-card p { margin:0; }
.login-card label { display:grid; gap:4px; font-size:13px; color:var(--muted); }

/* header */
header { display:flex; align-items:center; gap:24px; padding:10px 20px; background:var(--card); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5; flex-wrap:wrap; }
.brand { font-weight:700; }
nav { display:flex; gap:4px; flex:1; flex-wrap:wrap; }
nav a { text-decoration:none; color:var(--muted); padding:6px 12px; border-radius:6px; }
nav a.on { background:var(--accent); color:var(--accent-ink); }
.who { color:var(--muted); font-size:13px; }
main { padding:16px 20px 40px; max-width:1300px; margin:0 auto; }

/* generic */
.card { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.card h3 { margin:0 0 10px; font-size:15px; display:flex; gap:10px; align-items:center; justify-content:space-between; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(460px,100%),1fr)); gap:14px; margin-bottom:14px; }
.kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:14px; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.kpi b { display:block; font-size:24px; } .kpi span { color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); font-size:13px; }
th { color:var(--muted); font-weight:500; }
tr.click { cursor:pointer; } tr.click:hover { background:var(--bar); }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; vertical-align:middle; }
.barrow { display:grid; grid-template-columns:110px 1fr 56px; gap:8px; align-items:center; margin:5px 0; font-size:13px; }
.bar { height:16px; border-radius:4px; background:var(--accent); }
.toolbar { display:flex; gap:14px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
.toolbar label { display:flex; gap:6px; align-items:center; color:var(--muted); font-size:13px; }
.pager { display:flex; gap:8px; margin-top:10px; }

/* heat matrix */
.mx { display:grid; gap:2px; font-size:11px; }
.mx div { padding:6px 2px; text-align:center; border-radius:3px; }
.mx .h { color:var(--muted); background:none; }

/* network */
.netwrap { position:relative; background:var(--card); border:1px solid var(--line); border-radius:10px; height:calc(100vh - 190px); min-height:420px; overflow:hidden; }
#net { width:100%; height:100%; display:block; }
.legend { position:absolute; top:10px; left:12px; font-size:12px; background:color-mix(in srgb,var(--card) 85%,transparent); padding:6px 8px; border-radius:8px; }
.legend div { margin:2px 0; }
.tip { position:absolute; pointer-events:none; background:var(--ink); color:var(--bg); padding:5px 8px; border-radius:6px; font-size:12px; white-space:nowrap; }
.hint { position:absolute; bottom:6px; left:12px; margin:0; font-size:11px; color:var(--muted); }

/* communities */
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; margin-bottom:14px; }
.cc { background:var(--card); border:1px solid var(--line); border-top:5px solid var(--accent); border-radius:10px; padding:12px 14px; cursor:pointer; }
.cc:hover { box-shadow:0 2px 10px rgba(0,0,0,.15); } .cc.on { outline:2px solid var(--accent); }
.cc h4 { margin:0 0 6px; } .cc p { margin:2px 0; font-size:13px; color:var(--muted); }

/* drawer */
.drawer { position:fixed; right:0; top:0; bottom:0; width:min(380px,100%); background:var(--card); border-left:1px solid var(--line); padding:16px; overflow:auto; z-index:20; box-shadow:-6px 0 20px rgba(0,0,0,.2); }
.drawer h2 { margin:0; font-size:18px; } .drawer h4 { margin:16px 0 6px; font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
.close { position:absolute; right:10px; top:10px; }
.chip { display:inline-block; background:var(--bar); border-radius:12px; padding:1px 9px; font-size:12px; margin:2px 4px 2px 0; }
.post { border-bottom:1px solid var(--line); padding:6px 0; font-size:13px; } .post small { color:var(--muted); }
.friend { display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--line); cursor:pointer; } .friend:hover { color:var(--accent); }

@media (max-width:700px) { .kpis { grid-template-columns:repeat(2,1fr); } header { gap:8px; } main { padding:12px; } }
.fit { position:absolute; top:10px; right:12px; padding:5px 10px; font-size:12px; }
@media (max-width:700px) { nav a { padding:6px 9px; } .brand { width:100%; } }

/* join page */
.formgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; }
.formgrid label { display:grid; gap:3px; font-size:12px; color:var(--muted); }
#joinForm h4, #joinResult h4 { margin:14px 0 6px; font-size:13px; }
.taggroup { margin:4px 0; font-size:12px; color:var(--muted); }
.chips { display:flex; flex-wrap:wrap; gap:4px; margin:4px 0; }
.chips .chip { cursor:pointer; user-select:none; border:1px solid transparent; }
.chips .chip.sel { background:var(--accent); color:var(--accent-ink); }
.results .friend { padding:5px 6px; } .results { max-height:170px; overflow:auto; }
.big { font-size:22px; font-weight:700; margin:0 0 6px; }
.pick { display:flex; gap:8px; align-items:flex-start; padding:5px 0; border-bottom:1px solid var(--line); font-size:13px; }
.pick small { color:var(--muted); display:block; }
.ok { background:color-mix(in srgb,#2e9b5f 15%,var(--card)); border:1px solid #2e9b5f; border-radius:8px; padding:12px; }
.legend2 { font-size:12px; margin-top:4px; }
#spreadBar { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; }
'''

APP_JS = r'''/* Community Explorer -- Stage 7 (pages) + Stage 8 (talks to the Flask API with fetch).
   No build tools. Plain JavaScript + D3 (force layout and zoom), drawing the graph on a <canvas>. */
"use strict";

// ------------------------------------------------------------------ helpers
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = n => Number(n).toLocaleString();

async function api(url) {                                   // one place where every call to the server happens
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `server answered ${r.status}`);
  return body;
}

const INTEREST_COLORS = { Fashion: "#4c78a8", Food: "#f58518", Music: "#54a24b", Sports: "#e45756", Tech: "#72b7b2", Travel: "#b279a2" };
const TYPE_COLORS = { personal: "#4c78a8", creator: "#f58518", business: "#54a24b" };
const GREY = "#8a94a6";
let communities = [], commColor = { Isolated: GREY }, stats = null, inited = false;
const real = () => communities.filter(c => c.community_id !== "Isolated");       // communities with 2+ users

const dot = c => `<span class="dot" style="background:${c}"></span>`;
const commName = id => { const c = communities.find(x => x.community_id === id); return c && c.main_interest ? `${id} · ${c.main_interest}` : id; };
const fill = (sel, opts) => { sel.innerHTML = opts.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join(""); };

function bars(el, items, color) {                            // simple horizontal bar chart made of divs
  const max = Math.max(...items.map(i => i.value), 1);
  el.innerHTML = items.map(i => `<div class="barrow"><span>${i.label}</span>
      <div><div class="bar" style="width:${100 * i.value / max}%;background:${i.color || color || "var(--accent)"}"></div></div><b>${fmt(i.value)}</b></div>`).join("");
}

// ------------------------------------------------------------------ login (demo only)
const saved = () => { try { return sessionStorage.getItem("gv_user"); } catch { return null; } };
$("#loginForm").addEventListener("submit", e => {
  e.preventDefault();
  if ($("#user").value.trim() === "demo" && $("#pass").value === "graph123") {
    try { sessionStorage.setItem("gv_user", "demo"); } catch { /* private mode: still let them in */ }
    start();
  } else $("#loginErr").textContent = "Wrong username or password.";
});
$("#logout").addEventListener("click", () => { try { sessionStorage.removeItem("gv_user"); } catch { } location.hash = ""; location.reload(); });

async function start() {
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#whoName").textContent = "signed in as demo";
  if (!inited) {
    inited = true;
    try {
      [stats, { communities }] = await Promise.all([api("/api/stats"), api("/api/communities")]);
    } catch (err) {
      $("main").innerHTML = `<div class="card"><h3>Cannot reach the API</h3><p>${esc(err.message)}</p><p class="muted">Start the server with <code>python stage6_api.py</code> and open <code>http://127.0.0.1:5000</code>.</p></div>`;
      return;
    }
    communities.forEach(c => commColor[c.community_id] = INTEREST_COLORS[c.main_interest] || GREY);
    setupControls();
  }
  route();
}
if (saved()) start(); else $("#login").classList.remove("hidden");

// ------------------------------------------------------------------ router
window.addEventListener("hashchange", () => saved() && inited && route());
const built = {};
function route() {
  const [tab0, qs] = location.hash.slice(1).split("?");
  const tab = ["dashboard", "network", "communities", "users", "spread", "join"].includes(tab0) ? tab0 : "dashboard";
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("hidden", s.id !== "tab-" + tab));
  document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === tab));
  if (tab === "dashboard" && !built.dashboard) { built.dashboard = 1; renderDashboard(); }
  if (tab === "communities" && !built.communities) { built.communities = 1; renderCommunityCards(); }
  if (tab === "users" && !built.users) { built.users = 1; loadUsers(); }
  if (tab === "spread" && !built.spread) { built.spread = 1; setupSpread(); }
  if (tab === "join" && !built.join) { built.join = 1; setupJoin(); }
  if (tab === "network") {
    const p = new URLSearchParams(qs || "");
    if (p.get("community") !== null) $("#netCommunity").value = p.get("community");
    if (!built.network || p.get("community") !== null) { built.network = 1; resizeNet(); loadNetwork(p.get("focus")); }
    else resizeNet();
  }
}

// ------------------------------------------------------------------ fill the dropdowns, attach events
function setupControls() {
  const opts = [["", "all"], ...real().map(c => [c.community_id, commName(c.community_id)])];
  fill($("#netCommunity"), opts); fill($("#tagCommunity"), opts);
  fill($("#uc"), [...opts, ["Isolated", "Isolated (no friends)"]]);
  fill($("#ui"), [["", "all"], ...Object.keys(INTEREST_COLORS).map(i => [i, i])]);
  $("#tagCommunity").onchange = renderTags;
  $("#netCommunity").onchange = () => loadNetwork();
  $("#netColor").onchange = () => { drawLegend(); draw(); };
  $("#netGroup").onchange = () => { applyForces(); net.sim && net.sim.alpha(0.6).restart(); };
  for (const [id, out] of [["netMin", "netMinOut"], ["netLimit", "netLimitOut"]]) {
    $("#" + id).oninput = e => $("#" + out).textContent = e.target.value;
    $("#" + id).onchange = () => loadNetwork();
  }
  $("#netSearch").addEventListener("keydown", async e => {
    if (e.key !== "Enter") return;
    const q = e.target.value.trim(); if (!q) return;
    try {
      const r = await api(`/api/users?q=${encodeURIComponent(q)}&limit=1`);
      if (!r.users.length) { $("#netInfo").textContent = `no user matches "${q}"`; return; }
      focusUser(r.users[0].user_id);
    } catch (err) { $("#netInfo").textContent = err.message; }
  });
  let t; const debounce = () => { clearTimeout(t); t = setTimeout(() => { usersState.offset = 0; loadUsers(); }, 250); };
  $("#uq").oninput = debounce; ["uc", "ui", "us"].forEach(i => $("#" + i).onchange = debounce);
  $("#uprev").onclick = () => { usersState.offset = Math.max(0, usersState.offset - usersState.limit); loadUsers(); };
  $("#unext").onclick = () => { usersState.offset += usersState.limit; loadUsers(); };
  $("#fitBtn").onclick = () => fitView(true);
  $("#closeDrawer").onclick = () => { $("#drawer").classList.add("hidden"); net.selected = null; draw(); };
  window.addEventListener("resize", () => { resizeNet(); });
}

// ------------------------------------------------------------------ DASHBOARD
async function renderDashboard() {
  const s = stats;
  const k = [[fmt(s.users), "users"], [fmt(s.friendships), "friendships"], [fmt(s.posts), "posts"], [s.communities, "communities found"],
             [s.average_degree, "average friends per user"], [(s.density * 100).toFixed(2) + "%", "network density"],
             [(s.share_friendships_inside_communities * 100).toFixed(0) + "%", "friendships inside a community"], [s.isolated_users, "users with no friends"]];
  $("#kpis").innerHTML = k.map(([v, l]) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join("");
  bars($("#sizeBars"), real().map(c => ({ label: `${dot(commColor[c.community_id])}${esc(commName(c.community_id))}`, value: c.users, color: commColor[c.community_id] })));

  try {
    const { links } = await api("/api/community_links");
    const ids = real().map(c => c.community_id), M = {};
    ids.forEach(a => { M[a] = {}; ids.forEach(b => M[a][b] = 0); });
    links.forEach(l => { if (M[l.a] && M[l.b]) { M[l.a][l.b] += l.friendships; if (l.a !== l.b) M[l.b][l.a] += l.friendships; } });
    let max = 1; ids.forEach(a => ids.forEach(b => max = Math.max(max, M[a][b])));
    let h = `<div class="mx" style="grid-template-columns:70px repeat(${ids.length},1fr)"><div class="h"></div>` + ids.map(b => `<div class="h">${b}</div>`).join("");
    ids.forEach(a => {
      h += `<div class="h">${a}</div>` + ids.map(b => {
        const v = M[a][b], pct = Math.round(100 * Math.log1p(v) / Math.log1p(max));
        return `<div title="${a} - ${b}: ${v} friendships" style="background:color-mix(in srgb,var(--accent) ${pct}%,transparent)">${v}</div>`;
      }).join("");
    });
    $("#matrix").innerHTML = h + "</div>";
  } catch (err) { $("#matrix").textContent = err.message; }

  const top = await api("/api/users?limit=10&sort=degree");
  $("#topUsers").innerHTML = `<tr><th>User</th><th>City</th><th>Community</th><th>Friends</th></tr>` + top.users.map(u =>
    `<tr class="click" data-id="${u.user_id}"><td>${esc(u.username)}</td><td>${esc(u.city)}</td><td>${dot(commColor[u.community_id])}${esc(u.community_id)}</td><td>${u.degree}</td></tr>`).join("");
  $("#topUsers").onclick = e => { const tr = e.target.closest("tr[data-id]"); if (tr) openProfile(tr.dataset.id); };
  renderTags();
}

async function renderTags() {
  const c = $("#tagCommunity").value;
  const r = await api(`/api/hashtags?limit=10${c ? "&community=" + c : ""}`);
  bars($("#tagBars"), r.hashtags.map(h => ({ label: esc(h.hashtag), value: h.uses, color: c ? commColor[c] : undefined })));
}

// ------------------------------------------------------------------ COMMUNITIES
function renderCommunityCards() {
  $("#commCards").innerHTML = real().map(c => `<div class="cc" data-id="${c.community_id}" style="border-top-color:${commColor[c.community_id]}">
      <h4>${esc(commName(c.community_id))}</h4><p><b>${fmt(c.users)}</b> users, mostly in ${esc(c.main_city)}</p>
      <p>${c.interest_share}% share the main interest</p><p>average age ${c.avg_age}</p>
      <p>${c.inside_share}% of friendships stay inside</p><p>top user: ${esc(c.top_user)}</p></div>`).join("");
  $("#commCards").onclick = e => { const c = e.target.closest(".cc"); if (c) showCommunity(c.dataset.id); };
}

async function showCommunity(id) {
  document.querySelectorAll(".cc").forEach(x => x.classList.toggle("on", x.dataset.id === id));
  const c = await api(`/api/communities/${id}`), box = $("#commDetail");
  box.classList.remove("hidden");
  box.innerHTML = `<h3>${dot(commColor[id])}${esc(commName(id))} <button id="toNet">View in network</button></h3>
    <div class="grid2"><div><h4>Most connected users</h4><table>${c.top_users.map(u =>
      `<tr class="click" data-id="${u.user_id}"><td>${esc(u.username)}</td><td>${esc(u.city)}</td><td>${u.degree} friends</td></tr>`).join("")}</table></div>
    <div><h4>Top hashtags</h4><div id="cTags"></div></div></div>
    <h4>Friendships with other communities</h4><div id="cLinks"></div>`;
  bars($("#cTags", box), c.top_hashtags.map(h => ({ label: esc(h.hashtag), value: h.uses, color: commColor[id] })));
  bars($("#cLinks", box), c.links_to_other_communities.map(l => ({ label: `${dot(commColor[l.other_community])}${esc(commName(l.other_community))}`, value: l.friendships, color: commColor[l.other_community] })));
  $("#toNet", box).onclick = () => { location.hash = `#network?community=${id}`; };
  box.onclick = e => { const tr = e.target.closest("tr[data-id]"); if (tr) openProfile(tr.dataset.id); };
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ------------------------------------------------------------------ USERS table
const usersState = { offset: 0, limit: 15, total: 0 };
async function loadUsers() {
  const p = new URLSearchParams({ limit: usersState.limit, offset: usersState.offset, sort: $("#us").value });
  if ($("#uq").value.trim()) p.set("q", $("#uq").value.trim());
  if ($("#uc").value) p.set("community", $("#uc").value);
  if ($("#ui").value) p.set("interest", $("#ui").value);
  try {
    const r = await api("/api/users?" + p);
    usersState.total = r.total;
    $("#userTable").innerHTML = `<tr><th>Username</th><th>Name</th><th>City</th><th>Interest</th><th>Community</th><th>Age</th><th>Friends</th></tr>` +
      r.users.map(u => `<tr class="click" data-id="${u.user_id}"><td>${esc(u.username)}</td><td>${esc(u.full_name)}</td><td>${esc(u.city)}</td><td>${esc(u.interest)}</td>
        <td>${dot(commColor[u.community_id])}${esc(u.community_id)}</td><td>${u.age}</td><td>${u.degree}</td></tr>`).join("");
    const from = r.total ? usersState.offset + 1 : 0, to = Math.min(usersState.offset + usersState.limit, r.total);
    $("#uinfo").textContent = `showing ${from}-${to} of ${fmt(r.total)} users`;
    $("#uprev").disabled = usersState.offset === 0; $("#unext").disabled = to >= r.total;
    $("#userTable").onclick = e => { const tr = e.target.closest("tr[data-id]"); if (tr) openProfile(tr.dataset.id); };
  } catch (err) { $("#uinfo").textContent = err.message; }
}

// ------------------------------------------------------------------ PROFILE DRAWER
async function openProfile(id) {
  const d = $("#drawer"), body = $("#drawerBody");
  d.classList.remove("hidden"); body.innerHTML = `<p class="muted">Loading...</p>`;
  try {
    const [u, f, s] = await Promise.all([api(`/api/users/${id}`), api(`/api/users/${id}/friends?limit=8`), api(`/api/users/${id}/suggestions?limit=5`)]);
    const person = (x, extra) => `<div class="friend" data-id="${x.user_id}"><span>${dot(commColor[x.community_id])}${esc(x.username)}</span><span class="muted">${extra}</span></div>`;
    body.innerHTML = `<h2>${esc(u.full_name)}</h2><div class="muted">@${esc(u.username)}${u.is_verified ? " · verified" : ""}</div>
      <p><span class="chip">${esc(u.city)}</span><span class="chip">${esc(u.interest)}</span><span class="chip">${esc(u.account_type)}</span><span class="chip">age ${u.age}</span>
      <span class="chip">joined ${esc(u.joined_date)}</span></p>
      <p>${dot(commColor[u.community_id])}<b>${esc(commName(u.community_id))}</b></p>
      <p><b>${u.degree}</b> friends: ${u.friends_in_own_community} inside their community, ${u.friends_outside_community} outside. ${u.post_count} posts.</p>
      <button id="focusBtn">Show in network</button>
      <h4>Most connected friends</h4>${f.friends.map(x => person(x, x.degree + " friends")).join("") || "<p class='muted'>no friends</p>"}
      <h4>People you may know</h4>${s.suggestions.map(x => person(x, x.mutual_friends + " mutual")).join("") || "<p class='muted'>no suggestions</p>"}
      <h4>Recent posts</h4>${u.recent_posts.map(p => `<div class="post">${esc(p.text)}<br><small>${esc(p.hashtags)} · ${p.likes} likes · ${esc(p.posted_at.slice(0, 10))}</small></div>`).join("") || "<p class='muted'>no posts</p>"}`;
    $("#focusBtn").onclick = () => focusUser(id);
    body.onclick = e => { const fr = e.target.closest(".friend"); if (fr) { selectNode(fr.dataset.id); openProfile(fr.dataset.id); } };
    selectNode(id);
  } catch (err) { body.innerHTML = `<p class="err">${esc(err.message)}</p>`; }
}

// ------------------------------------------------------------------ NETWORK (D3 force layout on a canvas)
const net = { nodes: [], links: [], adj: new Map(), byId: new Map(), sim: null, t: d3.zoomIdentity, hover: null, selected: null, w: 0, h: 0, dpr: 1 };
const canvas = $("#net"), ctx = canvas.getContext("2d");
const radius = d => 2.5 + Math.sqrt(d.degree) * 0.9 + (net.spread && net.spread.seeds.has(d.id) ? 3 : 0);
const colorOf = d => spreadColor(d) || ($("#netColor").value === "account_type" ? (TYPE_COLORS[d.account_type] || GREY) : (commColor[d.community] || GREY));

function resizeNet() {
  const r = canvas.parentElement.getBoundingClientRect();
  if (!r.width) return;
  net.dpr = window.devicePixelRatio || 1; net.w = r.width; net.h = r.height;
  canvas.width = r.width * net.dpr; canvas.height = r.height * net.dpr;
  applyForces(); draw();
}

function applyForces() {
  if (!net.sim) return;
  const group = $("#netGroup").checked, ids = [...new Set(net.nodes.map(n => n.community))];
  const R = Math.min(net.w, net.h) * 0.3, centre = {};
  ids.forEach((c, i) => { const a = 2 * Math.PI * i / ids.length; centre[c] = ids.length > 1 ? [R * Math.cos(a), R * Math.sin(a)] : [0, 0]; });
  const s = group ? 0.08 : 0.02;
  net.sim.force("x", d3.forceX(d => group ? centre[d.community][0] : 0).strength(s))
         .force("y", d3.forceY(d => group ? centre[d.community][1] : 0).strength(s));
}

async function loadNetwork(focusId) {
  const p = new URLSearchParams({ min_degree: $("#netMin").value, limit: $("#netLimit").value });
  if ($("#netCommunity").value) p.set("community", $("#netCommunity").value);
  $("#netInfo").textContent = "loading...";
  try {
    const r = await api("/api/network?" + p);
    if (net.sim) net.sim.stop();
    net.nodes = r.nodes; net.links = r.links.map(l => ({ ...l }));
    net.byId = new Map(net.nodes.map(n => [n.id, n])); net.adj = new Map(net.nodes.map(n => [n.id, new Set()]));
    net.links.forEach(l => { net.adj.get(l.source).add(l.target); net.adj.get(l.target).add(l.source); });
    net.hover = null; net.selected = null;
    net.sim = d3.forceSimulation(net.nodes)
      .force("link", d3.forceLink(net.links).id(d => d.id).distance(28).strength(0.25))
      .force("charge", d3.forceManyBody().strength(-22).distanceMax(220))
      .force("collide", d3.forceCollide(d => radius(d) + 0.8))
      .alphaDecay(0.03).on("tick", draw).on("end", () => fitView(false));
    resizeNet(); net.sim.alpha(1).restart();
    net.t = d3.zoomIdentity.translate(net.w / 2, net.h / 2);
    d3.select(canvas).call(zoom.transform, net.t);
    $("#netInfo").textContent = `${fmt(r.node_count)} users and ${fmt(r.link_count)} friendships shown` + (r.node_count >= +$("#netLimit").value && r.node_count < stats.users && !$("#netCommunity").value ? " (most connected users; raise 'Max users' to see more)" : "");
    drawLegend();
    if (focusId) focusUser(focusId);
    if (pendingSpread) { pendingSpread = false; runSpread(); }
  } catch (err) { $("#netInfo").textContent = err.message; }
}

function fitView(animate = true) {                        // zoom so that the whole drawing fills the canvas
  if (!net.nodes.length || !net.w || net.dragging) return;
  const xs = net.nodes.map(n => n.x), ys = net.nodes.map(n => n.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const k = Math.min(4, 0.9 * Math.min(net.w / Math.max(x1 - x0, 1), net.h / Math.max(y1 - y0, 1)));
  const t = d3.zoomIdentity.translate(net.w / 2 - k * (x0 + x1) / 2, net.h / 2 - k * (y0 + y1) / 2).scale(k);
  const sel = d3.select(canvas); (animate ? sel.transition().duration(500) : sel).call(zoom.transform, t);
}

function drawLegend() {
  const byType = $("#netColor").value === "account_type";
  const items = byType ? Object.entries(TYPE_COLORS).map(([k, c]) => [k, c])
                       : [...new Set(net.nodes.map(n => n.community))].sort().map(c => [commName(c), commColor[c] || GREY]);
  $("#legend").innerHTML = items.map(([t, c]) => `<div>${dot(c)}${esc(t)}</div>`).join("");
}

function draw() {
  const { w, h, dpr, t } = net;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  ctx.save(); ctx.translate(t.x, t.y); ctx.scale(t.k, t.k);
  const focus = net.hover || net.selected, keep = focus ? new Set([focus, ...(net.adj.get(focus) || [])]) : null;
  const edgeColor = getComputedStyle(document.body).getPropertyValue("--muted") || "#888";
  ctx.lineWidth = 0.6 / t.k; ctx.strokeStyle = edgeColor;
  ctx.globalAlpha = keep ? 0.05 : 0.16; ctx.beginPath();
  for (const l of net.links) { if (keep && (l.source.id === focus || l.target.id === focus)) continue; ctx.moveTo(l.source.x, l.source.y); ctx.lineTo(l.target.x, l.target.y); }
  ctx.stroke();
  if (keep) {                                              // the focused user's own friendships, drawn strong
    ctx.globalAlpha = 0.8; ctx.lineWidth = 1.2 / t.k; ctx.beginPath();
    for (const l of net.links) if (l.source.id === focus || l.target.id === focus) { ctx.moveTo(l.source.x, l.source.y); ctx.lineTo(l.target.x, l.target.y); }
    ctx.stroke();
  }
  for (const n of net.nodes) {
    ctx.globalAlpha = keep && !keep.has(n.id) ? 0.15 : 1;
    ctx.beginPath(); ctx.arc(n.x, n.y, radius(n), 0, 6.2832); ctx.fillStyle = colorOf(n); ctx.fill();
    if ((net.spread && net.spread.seeds.has(n.id)) || n.id === net.selected || n.id === net.hover) { ctx.lineWidth = 2 / t.k; ctx.strokeStyle = "#111"; ctx.stroke(); }
  }
  ctx.restore();
}

const zoom = d3.zoom().scaleExtent([0.2, 10]).on("zoom", e => { net.t = e.transform; draw(); });
const nodeAt = (x, y) => net.sim ? net.sim.find(net.t.invertX(x), net.t.invertY(y), 10 / net.t.k) : undefined;
d3.select(canvas)
  .call(d3.drag().container(canvas)
    .subject(e => nodeAt(e.x, e.y))
    .on("start", e => { if (!e.active) net.sim.alphaTarget(0.3).restart(); e.subject.fx = net.t.invertX(e.x); e.subject.fy = net.t.invertY(e.y); })
    .on("drag", e => { e.subject.fx = net.t.invertX(e.x); e.subject.fy = net.t.invertY(e.y); })
    .on("end", e => { if (!e.active) net.sim.alphaTarget(0); e.subject.fx = null; e.subject.fy = null; }))
  .call(zoom)
  .on("dblclick.zoom", null);

canvas.addEventListener("mousemove", e => {
  const r = canvas.getBoundingClientRect(), n = nodeAt(e.clientX - r.left, e.clientY - r.top), tip = $("#tip");
  const id = n ? n.id : null;
  if (id !== net.hover) { net.hover = id; draw(); }
  if (n) { tip.classList.remove("hidden"); tip.textContent = `${n.username} · ${commName(n.community)} · ${n.degree} friends`;
           tip.style.left = Math.min(e.clientX - r.left + 14, net.w - 240) + "px"; tip.style.top = (e.clientY - r.top + 12) + "px"; }
  else tip.classList.add("hidden");
  canvas.style.cursor = n ? "pointer" : "grab";
});
canvas.addEventListener("mouseleave", () => { net.hover = null; $("#tip").classList.add("hidden"); draw(); });
canvas.addEventListener("click", e => {
  const r = canvas.getBoundingClientRect(), n = nodeAt(e.clientX - r.left, e.clientY - r.top);
  if (n) openProfile(n.id); else if (net.hover) openProfile(net.hover);
});

function selectNode(id) { net.selected = net.byId.has(id) ? id : null; draw(); }

async function focusUser(id) {
  // Already drawn? Centre on them. Otherwise open the network tab on their community and focus after it has loaded.
  if (!(location.hash.startsWith("#network") && net.byId.has(id))) {
    const u = await api(`/api/users/${id}`);
    if (u.degree === 0) { $("#netInfo").textContent = "this user has no friends yet, so they are not part of the drawing"; openProfile(id); return; }
    $("#netMin").value = 0; $("#netMinOut").textContent = "0";
    const target = `#network?community=${u.community_id}&focus=${id}`;
    if (location.hash === target) route(); else location.hash = target;
    return;
  }
  const n = net.byId.get(id);
  net.selected = id;
  setTimeout(() => {
    const k = 2.2;
    d3.select(canvas).transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(net.w / 2 - n.x * k, net.h / 2 - n.y * k).scale(k));
  }, 400);
  openProfile(id);
}

// ------------------------------------------------------------------ JOIN: predict community, recommend people, create the user
const join = { meta: null, tags: new Set(), friends: new Map(), profile: null, pred: null };

async function refreshData() {                                   // after the database changed: reload numbers, redraw everything
  [stats, { communities }] = await Promise.all([api("/api/stats"), api("/api/communities")]);
  communities.forEach(c => commColor[c.community_id] = INTEREST_COLORS[c.main_interest] || GREY);
  built.dashboard = built.communities = built.users = built.network = 0;
}

async function setupJoin() {
  try { join.meta = await api("/api/meta"); } catch (err) { $("#jErr").textContent = err.message; return; }
  const m = join.meta;
  fill($("#jCity"), m.cities.map(c => [c, c])); fill($("#jInterest"), m.interests.map(c => [c, c]));
  fill($("#jType"), m.account_types.map(c => [c, c]));
  $("#jTags").innerHTML = Object.entries(m.hashtags_by_interest).map(([i, tags]) =>
    `<div class="taggroup">${dot(INTEREST_COLORS[i] || GREY)}${esc(i)}<div class="chips">${tags.map(t => `<span class="chip" data-tag="${esc(t)}">${esc(t)}</span>`).join("")}</div></div>`).join("");
  $("#jTags").onclick = e => {
    const c = e.target.closest("[data-tag]"); if (!c) return;
    const t = c.dataset.tag;
    if (join.tags.has(t)) join.tags.delete(t); else if (join.tags.size < m.max_hashtags) join.tags.add(t);
    document.querySelectorAll("#jTags [data-tag]").forEach(x => x.classList.toggle("sel", join.tags.has(x.dataset.tag)));
    staleResult();
  };
  let timer;
  $("#jFriendQ").oninput = e => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = e.target.value.trim();
      if (q.length < 2) { $("#jFriendRes").innerHTML = ""; return; }
      const r = await api(`/api/users?q=${encodeURIComponent(q)}&limit=6&sort=degree`);
      $("#jFriendRes").innerHTML = r.users.filter(u => u.degree > 0).map(u => `<div class="friend" data-id="${u.user_id}" data-name="${esc(u.username)}" data-c="${u.community_id}">
          <span>${dot(commColor[u.community_id])}${esc(u.username)} <span class="muted">(${esc(u.full_name)}, ${esc(u.city)})</span></span><span class="muted">${u.degree} friends</span></div>`).join("") || "<p class='muted small'>no match</p>";
    }, 250);
  };
  $("#jFriendRes").onclick = e => {
    const f = e.target.closest(".friend"); if (!f) return;
    if (join.friends.size < m.max_friends) join.friends.set(f.dataset.id, { name: f.dataset.name, c: f.dataset.c });
    $("#jFriendQ").value = ""; $("#jFriendRes").innerHTML = ""; drawFriendChips(); staleResult();
  };
  $("#jFriends").onclick = e => { const c = e.target.closest("[data-id]"); if (c) { join.friends.delete(c.dataset.id); drawFriendChips(); staleResult(); } };
  $("#jUser").onblur = async () => {
    const u = $("#jUser").value.trim().toLowerCase(); if (!u) { $("#jUserMsg").textContent = ""; return; }
    const r = await api(`/api/username_available?u=${encodeURIComponent(u)}`);
    $("#jUserMsg").textContent = r.available ? "available" : "already taken";
  };
  $("#joinForm").addEventListener("input", staleResult);
  $("#joinForm").addEventListener("submit", e => { e.preventDefault(); runPrediction(); });
}

function drawFriendChips() {
  $("#jFriends").innerHTML = [...join.friends].map(([id, f]) => `<span class="chip" data-id="${id}" title="click to remove">${dot(commColor[f.c])}${esc(f.name)} ✕</span>`).join("");
}
const staleResult = () => { if (join.pred) { join.pred = null; $("#joinResult").classList.add("hidden"); } };

function formProfile() {
  return { full_name: $("#jName").value.trim(), username: $("#jUser").value.trim().toLowerCase(), age: $("#jAge").value, city: $("#jCity").value,
           interest: $("#jInterest").value, account_type: $("#jType").value, hashtags: [...join.tags], friend_ids: [...join.friends.keys()] };
}

async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `server answered ${r.status}`);
  return data;
}

async function runPrediction() {
  $("#jErr").textContent = "";
  join.profile = formProfile();
  try { join.pred = await post("/api/predict", join.profile); } catch (err) { $("#jErr").textContent = err.message; return; }
  const p = join.pred, best = p.probabilities[0];
  const words = s => s < 0.7 ? "slightly" : s < 2 ? "clearly" : "strongly";
  const pick = (x, on) => `<label class="pick"><input type="checkbox" value="${x.user_id}" ${on ? "checked" : ""}>
      <span>${dot(commColor[x.community_id])}<b>${esc(x.username)}</b> <span class="muted">${esc(x.community_id)} · ${x.degree} friends · ${esc(x.city)}</span><small>${esc(x.reason)}</small></span></label>`;
  const box = $("#joinResult"); box.classList.remove("hidden");
  box.innerHTML = `<h3>Our prediction</h3>
    <p class="big">${dot(commColor[p.predicted_community])}${esc(commName(p.predicted_community))} <span class="muted">${(100 * p.confidence).toFixed(p.confidence > 0.995 ? 1 : 0)}%</span></p>
    <div id="pBars"></div>
    <h4>Why</h4><ul>${p.why.map(w => `<li>${esc(w.factor)} ${words(w.strength)} points to ${esc(w.pushes_towards)}</li>`).join("")}</ul>
    <h4>Join community</h4><select id="jComm">${p.probabilities.map(x => `<option value="${x.community_id}">${esc(commName(x.community_id))} (${Math.round(100 * x.probability)}%)</option>`).join("")}</select>
    <span class="muted small">(you can override the prediction)</span>
    <h4>People we suggest you connect with</h4><div id="pMain">${p.recommended_people.map((x, i) => pick(x, i < 3)).join("")}</div>
    <h4>Explore beyond your community</h4><div id="pBridge">${p.bridge_people.map(x => pick(x, false)).join("") || "<p class='muted small'>none</p>"}</div>
    <p><button id="createBtn">Create my account</button> <span id="cErr" class="err"></span></p>
    <p class="muted small">This saves you in the database, connects you with everybody you know or ticked, and updates the friend counts and community statistics.</p>`;
  bars($("#pBars"), p.probabilities.map(x => ({ label: `${dot(commColor[x.community_id])}${esc(commName(x.community_id))}`, value: Math.round(1000 * x.probability) / 10, color: commColor[x.community_id] })));
  $("#createBtn").onclick = createAccount;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function createAccount() {
  const ticked = [...document.querySelectorAll("#pMain input:checked, #pBridge input:checked")].map(i => i.value);
  const body = { ...join.profile, community_id: $("#jComm").value, friend_ids: [...new Set([...join.profile.friend_ids, ...ticked])] };
  $("#createBtn").disabled = true; $("#cErr").textContent = "";
  try {
    const r = await post("/api/users", body);
    await refreshData();
    $("#joinResult").innerHTML = `<div class="ok"><h3>Welcome, @${esc(r.username)}!</h3>
      <p>Your account <b>${esc(r.user_id)}</b> was saved in the database. You joined <b>${esc(commName(r.community_id))}</b> and are connected with <b>${r.connected_to.length}</b> people.</p>
      <p><button id="seeMe">Show me in the network</button> <button id="seeProfile" class="link">Open my profile</button> <button id="another" class="link">Add another user</button></p></div>`;
    $("#seeMe").onclick = () => focusUser(r.user_id);
    $("#seeProfile").onclick = () => openProfile(r.user_id);
    $("#another").onclick = () => { join.tags.clear(); join.friends.clear(); join.pred = null; $("#joinForm").reset(); drawFriendChips(); document.querySelectorAll("#jTags .sel").forEach(x => x.classList.remove("sel")); $("#joinResult").classList.add("hidden"); };
  } catch (err) { $("#cErr").textContent = err.message; $("#createBtn").disabled = false; }
}

// ------------------------------------------------------------------ SPREAD (Stage 10): animate one cascade on the network
let pendingSpread = false, spreadTimer = null;
function spreadColor(d) {
  const s = net.spread; if (!s) return null;
  const r = s.round.get(d.id);
  if (r === undefined || r > s.upto) return "#c5cad4";                 // not reached (yet)
  return d3.interpolateInferno(0.05 + 0.75 * r / Math.max(s.max, 1));   // dark = early rounds, bright = late rounds
}

function clearSpread() {
  clearInterval(spreadTimer); net.spread = null; $("#spInfo").textContent = ""; drawLegend(); draw();
}

async function runSpread() {
  clearInterval(spreadTimer);
  const strat = $("#spStrategy").value, p = $("#spP").value, k = $("#spK").value;
  if (strat === "selected" && !net.selected) { $("#spInfo").textContent = "click a user in the network first"; return; }
  $("#spInfo").textContent = "simulating...";
  let r;
  try {
    r = await api(strat === "selected" ? `/api/spread?seeds=${net.selected}&p=${p}` : `/api/spread?strategy=${encodeURIComponent(strat)}&k=${k}&p=${p}`);
  } catch (err) { $("#spInfo").textContent = err.message; return; }
  const round = new Map(); r.rounds.forEach((ids, t) => ids.forEach(id => round.set(id, t)));
  net.spread = { round, seeds: new Set(r.seeds.map(s => s.user_id)), upto: -1, max: r.rounds.length - 1, res: r };
  let cum = 0;
  $("#legend").innerHTML += `<div style="margin-top:6px">${dot("#c5cad4")}not reached</div><div>${dot(d3.interpolateInferno(0.1))}early rounds</div><div>${dot(d3.interpolateInferno(0.8))}late rounds</div><div class="muted">ringed = seeds</div>`;
  spreadTimer = setInterval(() => {
    const s = net.spread; if (!s) return clearInterval(spreadTimer);
    s.upto++; cum += r.rounds[s.upto].length; draw();
    $("#spInfo").textContent = `round ${s.upto}: ${fmt(cum)} of ${fmt(r.users)} users have the post (${(100 * cum / r.users).toFixed(1)}%)`;
    if (s.upto >= s.max) {
      clearInterval(spreadTimer);
      const by = Object.entries(r.by_community).filter(([c]) => c !== "Isolated").map(([c, v]) => `${c} ${Math.round(100 * v.reached / v.users)}%`).join(", ");
      $("#spInfo").textContent = `done after ${r.n_rounds} rounds: ${fmt(r.reached)} of ${fmt(r.users)} users reached (${(100 * r.reached / r.users).toFixed(1)}%). By community: ${by}. Seeds: ${r.seeds.map(x => x.username).join(", ")}`;
    }
  }, 450);
}

$("#spGo").onclick = runSpread;
$("#spClear").onclick = clearSpread;
$("#spK").oninput = e => $("#spKOut").textContent = e.target.value;
$("#spP").oninput = e => $("#spPOut").textContent = e.target.value;

function lineChart(el, xs, series, colors) {
  const W = 480, H = 260, L = 44, B = 32, T = 10, R = 10;
  const ymax = Math.max(...Object.values(series).flat()) * 1.05 || 1;
  const X = i => L + (W - L - R) * i / (xs.length - 1), Y = v => T + (H - T - B) * (1 - v / ymax);
  let svg = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:520px">`;
  for (let g = 0; g <= 4; g++) { const v = ymax * g / 4; svg += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${Y(v) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">${Math.round(v)}</text>`; }
  xs.forEach((x, i) => svg += `<text x="${X(i)}" y="${H - 12}" font-size="10" text-anchor="middle" fill="var(--muted)">${x}</text>`);
  svg += `<text x="${(L + W) / 2}" y="${H - 1}" font-size="10" text-anchor="middle" fill="var(--muted)">users blocked</text>`;
  Object.entries(series).forEach(([name, ys], si) => {
    svg += `<polyline fill="none" stroke="${colors[si]}" stroke-width="2.2" points="${ys.map((v, i) => `${X(i)},${Y(v)}`).join(" ")}"/>` + ys.map((v, i) => `<circle cx="${X(i)}" cy="${Y(v)}" r="3" fill="${colors[si]}"><title>${name}: block ${xs[i]} -> ${v} users</title></circle>`).join("");
  });
  el.innerHTML = svg + `</svg><div class="legend2">${Object.keys(series).map((n, i) => `<span>${dot(colors[i])}${esc(n)}</span>`).join(" &nbsp; ")}</div>`;
}

function setupSpread() {
  $("#xK").oninput = e => $("#xKOut").textContent = e.target.value;
  $("#xP").oninput = e => $("#xPOut").textContent = e.target.value;
  $("#xGo").onclick = runExperiments;
  $("#xAnim").onclick = () => {
    pendingSpread = true; $("#spP").value = $("#xP").value; $("#spPOut").textContent = $("#xP").value; $("#spK").value = Math.min(10, $("#xK").value); $("#spKOut").textContent = $("#spK").value;
    $("#netLimit").value = 1000; $("#netLimitOut").textContent = "1000"; $("#netMin").value = 0; $("#netMinOut").textContent = "0";
    location.hash = "#network?community="; if (net.nodes.length && built.network) { built.network = 1; route(); }
  };
  runExperiments();
}

async function runExperiments() {
  $("#xInfo").textContent = "running the simulations (a few seconds)..."; $("#xGo").disabled = true;
  const k = $("#xK").value, p = $("#xP").value;
  try {
    const [c, b] = await Promise.all([api(`/api/spread/compare?k=${k}&p=${p}&trials=150`), api(`/api/spread/containment?p=${p}&trials=150`)]);
    const names = Object.keys(c.strategies).sort((x, y) => c.strategies[y].mean - c.strategies[x].mean);
    bars($("#xBars"), names.map(n => ({ label: esc(n), value: Math.round(c.strategies[n].mean), color: n === "random" ? "#8a94a6" : "var(--accent)" })));
    const best = c.strategies[names[0]], rnd = c.strategies.random;
    $("#xNoteA").textContent = `Average users reached out of 1,000 (${c.trials} runs each, p = ${c.p}). Best: "${names[0]}" with ${best.share}% of the network, against ${rnd.share}% for random users.`;
    lineChart($("#xLines"), b.blocked, b.average_reach, ["#8a94a6", "#4c78a8", "#e45756"]);
    const last = b.blocked.length - 1;
    $("#xNoteB").textContent = `A rumour starts at a random user. Blocking the ${b.blocked[last]} most connected users cuts its average reach from ${Math.round(b.average_reach["top degree"][0])} to ${Math.round(b.average_reach["top degree"][last])} users; blocking ${b.blocked[last]} random users only reaches ${Math.round(b.average_reach["random users"][last])}.`;
    $("#xInfo").textContent = "";
  } catch (err) { $("#xInfo").textContent = err.message; }
  $("#xGo").disabled = false;
}
'''

D3_MIN_JS_ZLIB_B64 = """
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
KfuPc0HPRkj7+fxuq+5/866+WlTk87kN0oL3t3Ub+qOWTL2Ya9X5l3O+SFeKQW/n+na9BvOFdef5xQaloueWUpEqyufa0n8xd5UO
fYK1rdXiaaW+nXci/+W8k7NOET1E3lt+G76em+sFOhUGncCroDUE5Xk0Fg2N0ECL5/rblsO9nmtFaLbpeEjVe6/nPCU/zeW4ptwT
8TXNELsI2m2sgHaFZWkz+GluDev37avnn7ClUXN+wnYlU0Ft+HquGM3P5tssvHTZ7+b/k4ZetOyoglVbL3PMNwfFHWKpxW/zdesv
S4C40fBL9+Gv+XZrpv/Y1ou68Nfc2BxtaPl2Yy8T62lr6/67LL6oiV99sImbjbp0+36d/4/aglHjfv1g4/6bDcQalNuCac0y+q61
jHacnZL2mN/mW2yuiAv6bd62oWyUk9sLEucDvUYtxeT5Sne003Dcypf2rXzmebxhAYqTMyBEMExdqzuI6al9F5jv9IN4uy6SIz4Z
5vzrRF7uJ8SH9vzaYtuhU4x7gEBq7vEi7iQN4IiIWT1Wjcp0e6R2cHvNwYC+JJr287ytO/zlvGXBqjL+PCcGV13NWFrwP1tZxyva
XdZV0S/zduCFOTOi/jRGlBKj1eN+wOg83xYcS+kourZW1O//c5Wlolyp7Nu5HQRgk7tcRGacErOzkE/hIvfwMU5z/f1HVjigmk7q
PWSFuLQ3kjPHrv+skXBQP5/Rcfpg4XYW1JSFy90o6j6r79XBhdu5oCZeqO+Y1laG9GDmdmbECs1cc2e1KfQYNuRPFhA1I/oYIIWr
kLKDqduZ0ohMPw7pwoYUN1dkV8xxFBt8KFDPt8VF+8hWXEIZ6E5c7WdVCejrwDUATT/bpceFkzcdRXiv2l0gROSWE6I6HepFG9Ih
jaVW/AM35ybzafAXO7o3r0nKr4OrVoLbQOcC93PBiWAFWmSHYAta4FdJ405dBNI4UBf5SaQ8fwgVVakkbuwk4KQKpkqgjHR6bDz2
OPCaMR7nopqIcURny4nVRjTaUnf+QBtT6UW6jSUeVRszncoqOCqVHtOTUrtxVtGII+IhWW6N661M6QttaiOduOH0XSSqjQjXfc85
QtZ6hvilmZ/m1TVQ/8HcLNQsEBnhKaBz+WC8EBd1A1eG8EOgZhrU1AI1E1MG1fhzrEHNPgBqKb0Z8d2/QHyaCNjlxfJ3SHZLuA0q
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
mFbx8Gqj4eYRuJD7LItCxZPKp6/zrLH3S91VNqFjJeCxbkH2okD2yHwItkUefX4XeeMHIvzuLgqNByCUh6rGsBCu/T8OulAsB/rF
EBpGN0jH3Oqja//ov/45b/8z7hzpK7p5fKRf4/fsn//8r4/bndP3Z/88b2mHf9yeHykbSS6u17YgnRinBXqSOKfdfJhrHdxNq7ik
leUBQXAiTusdQKJL8RakqpponXSoLuAOrxvxLTMxuwqg365hB/zznx8/OVCSjtWkHHJEjJ4vZ62D/2qdDg86Oa+wC6+Lkg7eH4BA
7UA/SFUky3UkL2jbh9ziWYwywr9o2Er65FxT/e6bNd6M1q1V6FBzwy5mc2uL1VXr7Q9Au7gb7Zt7oLXW0P5wN9pnH4D2x7vRvv4A
tD/djfb5PdA6a2hXd6N9+QHUFmg7Lf556vVPyRIbWsLW9hX1bq2oo/9q/aK9b511uuf/jP8Za+gCw9MWX2qnR5tkeGtk/OJnZ+b5
qTHswjuwQE52Zp9DVRvGgbaXkE8/oJn+5tttQti192H+7gO4CZOE8Jr78P7+AXjjuyv/43ugtTfINfR7If/sA2j+8m60//gAtC/u
Rvv5B6B9fTfa3z6Aw9/ejfaHe6D1NtAq8z6E+ci8o8N+tVbK6q5+0sDVQPXqLoLXiP3+bh588kCU87tRvr1uOJ5kQdTOAcpSD6b+
dnvaYpxtLfGvexPDI3z/3rTW8ny5kcfswNeRi/pysgFoIedEt9UzWbeX01wotZbni2aeAkUHYhTGV72edgfmcv57jfifdhFSrMVa
S/7L9uSvFZLV5N80xv9Lj0kN+zU57Q2V6M/fb+BfNjjZNSUv1UK+3lvI5KlfOKWT02e08GT4bFWu11VOEL1YCw3GSHWU/2y9Jjst
h8Zt6K4qbJ2kyUXD0iyTKUeLXqx/582d35ldbOV97Tazl9jMk27kaRXfpt2Zd3p3ecJBHkfJE1w0D0dZrw1JgKjqRGzUiXZnGYuL
tfpeXwxVHjw2eSodCdrmAYYewETXOqBgcuSRc03jYpZ88Ngrb5UTvLZ/fjU0ssatZGfy7ZJmflf67cLm6mJT2KzKpiO2C5vLnUXt
lTdxM1uBZV3ezHYj3yFyRnvI2S51Vjtz7BI81+ttpBzG2SN7LjZK+bzB2G19MryrHFX8vOKm/mqL+Bmvix/GS+Ln1XrdSvEjSvFT
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
"""


def write_frontend(base=None, force=False):
    """Create <base>/frontend/ with all site files. Skips work if the folder is already up to date."""
    base = Path(base) if base else Path(__file__).resolve().parent
    root = base / "frontend"
    stamp = root / ".version"
    if not force and stamp.exists() and stamp.read_text().strip() == VERSION and (root / "vendor" / "d3.min.js").exists():
        return root
    (root / "vendor").mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (root / "app.js").write_text(APP_JS, encoding="utf-8")
    (root / "vendor" / "d3.min.js").write_bytes(zlib.decompress(base64.b64decode("".join(D3_MIN_JS_ZLIB_B64.split()))))
    stamp.write_text(VERSION)
    return root


if __name__ == "__main__":
    print("Frontend written to", write_frontend(force=True))
