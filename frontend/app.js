/* Community Explorer -- Stage 7 (pages) + Stage 8 (talks to the Flask API with fetch).
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
