// waku dashboard — formatters + chat card renderers + chatlog + streaming + send.
// Split out of app.js: classic <script>, shared global scope (no build
// step, no modules). Load order + rules: static/README.md.

const money = n => "$" + (n < 0.01 ? n.toFixed(4) : n.toFixed(2));
const secs = ms => ms==null ? "—" : (ms/1000).toFixed(1)+"s";

const gateBadge = g => !g ? "" :
  uiBadge("gate · " + esc(g.decision), g.decision === "retrieve" ? "live" : "neutral")
  + `<span class="meta" style="margin:0">${esc(g.reason||"")}</span>`;

// A tool call renders as a status row (dot + one-line summary); the raw output
// hides behind a disclosure so an ugly osascript error never floods the page.
const toolRow = x => `<div class="tool ${x.status||"ok"}">
  <div class="tool-head"><span class="dot ${x.status||"ok"}"></span><code>${esc(x.tool)}</code>
    ${x.summary?`<span style="color:var(--text-muted)">${esc(x.summary)}</span>`:""}</div>
  ${x.output!==undefined?`<details><summary>args &amp; raw output</summary>
    <pre>${esc(x.tool)}(${esc(JSON.stringify(x.args,null,1))})\n\n${esc(x.output)}</pre>
  </details>`:""}
</div>`;

// A stored history row -> a CHAT item. Assistant rows with saved telemetry
// (meta: gate/latency/iterations/tools) render as the FULL turn card, so a
// reopened thread looks just like when it was live. Rows without meta (from
// before this was saved, or another gateway) fall back to a plain card.
function histItem(m){
  if (m.role === "user") return {role:"user", text:m.content};
  if (m.meta) return {role:"waku", reply:stripTools(m.content), gate:m.meta.gate,
                      graph:m.meta.graph,
                      tools:m.meta.tools, iterations:m.meta.iterations,
                      latency_ms:m.meta.latency_ms, model:m.meta.model};
  return {role:"waku", reply:stripTools(m.content), historical:true};
}

const turnCard = t => uiCard(`
  <div class="u">${esc(t.user_message)}</div>
  <div class="meta" style="margin-top:var(--spacing)">${gateBadge(t.gate)}</div>
  ${(t.tools||[]).map(toolRow).join("")}
  <div class="r">${renderMarkdown(t.reply)}</div>
  <div class="meta">${esc((t.ts||"").replace("T"," ").slice(0,19))} · ${secs(t.latency_ms)} · ${t.iterations??"?"} iter · ${money(t.cost||0)}${t.consolidation?` · consolidated ${t.consolidation.new_facts} fact(s)`:""}</div>`);

// The reply's copy button. It sits inside the card, and CSS shows it only
// while the card is hovered (.card:hover .msg-copy).
const msgCopy = text => uiButton("Copy", {level: "tertiary", size: "sm", cls: "msg-copy",
  onclick: "copyMsg(this)", title: "Copy reply", attrs: `data-text="${esc(text)}"`});

// uiTable takes rows as arrays of cell HTML. A row may still arrive as a
// "<tr><td>…</td></tr>" string; parse it into its cells (a <td class> is kept
// as a span) so either shape renders the same table.
const rowCells = r => {
  if (typeof r !== "string") return r;
  const t = document.createElement("template");
  t.innerHTML = `<table><tbody>${r}</tbody></table>`;
  return [...t.content.querySelectorAll("td")].map(td =>
    td.className ? `<span class="${td.className}">${td.innerHTML}</span>` : td.innerHTML);
};
const table = (heads, rows) => uiTable(heads, rows.map(rowCells), {empty: "nothing here yet"});

// Two figures over a thin bar in the chart ramp. Shared by the retrieval gate
// (skip / retrieve) and the graph panel (quick / full); a and b are counts.
// With no turns yet the figures read "—" over an empty bar.
function splitFigures(aLabel, a, bLabel, b, ofText){
  const tot = a + b;
  const aPct = tot ? Math.round(a / tot * 100) : 0, bPct = tot ? 100 - aPct : 0;
  const fig = (label, pct) =>
    `<div><span class="stat-label">${label}</span><b class="gate-fig">${tot ? pct + "%" : "—"}</b></div>`;
  return `<div class="gate-figs">${fig(aLabel, aPct)}${fig(bLabel, bPct)}${
      tot && ofText ? `<span class="gate-of">${ofText}</span>` : ""}</div>`
    + `<div class="thinbar">${tot
      ? `<i style="flex:${aPct};background:var(--chart-1)"></i><i style="flex:${bPct};background:var(--chart-3)"></i>`
      : ""}</div>`;
}

const gateSplit = s => {
  const tot = s.gate_skips + s.gate_retrieves;
  const figs = splitFigures("Skip", s.gate_skips, "Retrieve", s.gate_retrieves, `of ${tot} turns`);
  if (!tot)
    return figs + `<div class="meta" style="margin-top:calc(var(--spacing) * 1.5)">no turns yet — send a message and the gate starts deciding</div>`;
  const skipPct = Math.round(s.gate_skips/tot*100);
  return figs + `<div class="meta" style="margin-top:calc(var(--spacing) * 1.5)">the retrieval gate skipped memory on ${skipPct}% of turns — that's latency and bias saved</div>`;
};

// --- Chat gateway: type here, watch the harness run (turns kept in memory)
const CHAT = [];
// The gate → tools → reply stage strip, shared by the live card and the
// completed/replayed card so the markup can't drift. `live` lights stages up
// (gate flips to done once decided, reply "on" once text streams); otherwise
// every stage is done and the strip carries the .tele class (hidden by the
// stats toggle). (.stages is flexbox, so inter-span whitespace is irrelevant.)
function stagesRow(t, live){
  // A stage that is running is "live", a finished one "ok", one not reached yet "neutral".
  const gateVariant = live && !t.gate ? "live" : "ok";
  const replyVariant = live ? (t.stream ? "live" : "neutral") : "ok";
  const tools = (t.tools||[]).map(x => toolChip(x.tool)).join("");
  // graph chip first — the front door. A quick graph turn has NO gate stage
  // (memory retrieval never ran), so the gate chip is honest and disappears.
  const graph = (t.graph && t.graph.route)
    ? uiBadge("graph · " + esc(t.graph.route), "ok") : "";
  const gate = (t.graph && t.graph.route === "quick") ? ""
    : uiBadge(`gate${t.gate?` · ${esc(t.gate.decision)}`:""}`, gateVariant);
  return `<div class="stages${live?"":" tele"}">`
    + graph + gate + tools + uiBadge("reply", replyVariant) + `</div>`;
}
// The per-turn telemetry footer: seconds · iterations · model · consolidation.
const teleFooter = t => `<div class="meta tele">${secs(t.latency_ms)} · ${t.iterations??"?"} iter${
  t.model?` · ${esc(t.model)}`:""}${t.consolidation?` · consolidated ${t.consolidation.new_facts} fact(s)`:""}</div>`;

// The agent's question with its choices (the ask_options tool): one button per
// choice, and "Other" for an answer in your own words. A pick is sent as your
// reply; once you answer anything, the buttons give way to the plain question.
const askRow = t => {
  if (!t.ask || !t.ask.options.length) return "";
  // the reply already ends with the question (the harness writes it there):
  // show the choices under it, not the question a second time
  const said = (t.reply || "").trim().endsWith((t.ask.question || "").trim());
  const q = said ? "" : `<div class="ask-q">${esc(t.ask.question)}</div>`;
  if (t.ask.answered) return `<div class="ask">${q}</div>`;
  return `<div class="ask">${q}<div class="ask-opts">`
    + t.ask.options.map(o => uiButton(esc(o), {onclick: "pickOption(this)", attrs: `data-v="${esc(o)}"`})).join("")
    + uiButton("Other&hellip;", {level: "tertiary", onclick: "pickOption(null)", title: "Type your own answer"})
    + `</div></div>`;
};
// The NIT the chat generated (waku/nam/nit.py), shown as the filled template
// beside the chat, NIT 65 : chat 35 (#nitpane, style.css). It opens the moment
// it is generated and refreshes after every answer or change (each "nit"
// event); the card's View NIT opens it again. Missing entries are asked for
// in the chat; Download PDF turns on once every entry is filled.
let NIT_OPEN = "", NIT_LABELS = {};
const nitUrl = id => `/api/nit/${encodeURIComponent(id)}`;
async function openNit(id){
  if (!/^NAM-\d{4}-\d{4,}$/.test(id || "")) return;
  NIT_OPEN = id;
  document.getElementById("nit-title").textContent = `NIT ${id}`;
  document.body.classList.remove("dock-closed", "dock-full");
  document.body.classList.add("nit-open");
  const sheet = document.getElementById("nit-sheet");
  if (!sheet.innerHTML) sheet.innerHTML = `<div class="empty">Loading the NIT&hellip;</div>`;
  try {
    const res = await fetch(`${nitUrl(id)}.json`);
    if (!res.ok) throw new Error(res.status);
    renderNit(await res.json());
  } catch (e) { sheet.innerHTML = `<div class="empty">Could not load the NIT (${esc(String(e.message || e))}).</div>`; }
}
function closeNit(){
  NIT_OPEN = "";
  document.body.classList.remove("nit-open");
  document.getElementById("nit-sheet").innerHTML = "";
}
function downloadNit(id, draft){
  if ((id = id || NIT_OPEN)) location.href = `${nitUrl(id)}.pdf?download=1${draft ? "&draft=1" : ""}`;
}
// A suggestion taken as it is, from the sheet.
async function acceptNit(rowId){
  const res = await fetch(`${nitUrl(NIT_OPEN)}/field`, {method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify({field: rowId, value: "accept"})});
  if (res.ok) renderNit(await res.json());
}
// A change or a missing entry goes through the chat, where the agent saves it.
function askNit(rowId, verb){
  const input = document.getElementById("dmsg");
  if (!input || !NIT_LABELS[rowId]) return;
  input.value = `${verb} ${NIT_LABELS[rowId]} to `;
  input.focus();
}
const nitCell = r => {
  const id = esc(r.id);
  if (r.kind === "fixed") return esc(r.value);
  if (r.kind === "missing")
    return `<span class="nit-gap">[TO BE FILLED]</span><div class="nit-acts">${
      uiButton("Fill", {size: "sm", onclick: `askNit('${id}', 'Set')`})}</div>`;
  if (r.kind === "suggested")
    return `<span class="nit-sugg">${esc(r.value.text)}</span><span class="nit-src">Suggested from ${esc(r.value.source)} in the KG</span>
      <div class="nit-acts">${uiButton("Accept", {size: "sm", level: "primary", onclick: `acceptNit('${id}')`})}${
        uiButton("Change", {size: "sm", onclick: `askNit('${id}', 'Change')`})}</div>`;
  // a filled entry reads as plain text; an accepted suggestion keeps its
  // source tender on the record (nam_nit_fields), not on the sheet
  return esc(r.value);
};
const nitRows = rows => rows.map(r => `<tr><th>${esc(r.label)}</th><td>${nitCell(r)}</td></tr>`).join("");
function renderNit(d){
  NIT_LABELS = {};
  [...d.header, ...d.sections.flatMap(s => s.rows), ...d.contacts.flatMap(c => c.rows)]
    .forEach(r => { NIT_LABELS[r.id] = r.full_label || r.label; });
  const head = Object.fromEntries(d.header.map(r => [r.id, r]));
  const ref = r => r && r.kind === "filled" ? esc(r.value) : `<span class="nit-gap">[TO BE FILLED]</span>`;
  const qty = q => q === null || q === undefined ? "" : esc(String(q));
  document.getElementById("nit-sheet").innerHTML = `<article class="nit-sheet">
    ${d.ready ? "" : `<div class="nit-stamp"><span>Draft &mdash; not for issue</span></div>`}
    <header class="nit-letter">
      <p class="nit-org">Numaligarh Refinery Limited</p>
      <p class="nit-sub">A Government of India Enterprise</p>
      <p class="nit-sub">Materials &amp; Contracts Department &middot; Numaligarh, Golaghat, Assam 785699</p>
    </header>
    <h2 class="nit-doc-title">${esc(d.title)}</h2>
    <div class="nit-refs"><span>Tender No: ${ref(head.tender_no)}</span><span>E-File Ref: ${ref(head.aan_file_number)}</span><span>Case: ${esc(d.case_id)}</span></div>
    <table class="nit-tbl" style="margin-top:var(--space-6)">${nitRows(d.header)}</table>
    <p class="nit-intro">${esc(d.intro)}</p>
    ${d.sections.map(s => `<h3 class="nit-sec">${esc(s.title)}</h3><table class="nit-tbl">${nitRows(s.rows)}</table>`).join("")}
    <h3 class="nit-sec">Contacts</h3>
    ${d.contacts.map(c => `<table class="nit-tbl"><tr><th colspan="2">${esc(c.title)}</th></tr>${nitRows(c.rows)}</table>`).join("")}
    <h3 class="nit-sec">Annexure &mdash; Schedule of items</h3>
    <table class="nit-tbl nit-items"><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit</th></tr>${
      d.items.map((x, i) => `<tr><td>${i + 1}</td><td>${esc(x.item)}</td><td>${qty(x.qty)}</td><td>${esc(x.uom || "")}</td></tr>`).join("")}</table>
    <p class="nit-prov">${esc(d.provenance)}</p>
  </article>`;
  document.getElementById("nit-status").textContent = d.ready ? "Ready to download"
    : `${d.missing.length} missing · ${d.suggested} to confirm`;
  const dl = document.getElementById("nit-download");
  dl.disabled = !d.ready;
  dl.title = d.ready ? "Download the NIT as PDF" : "Active once every entry is filled and every suggestion confirmed";
}
const nitRow = t => {
  if (!t.nit || !t.nit.case_id) return "";
  const n = t.nit, id = esc(n.case_id);
  return `<div class="ask nit"><div class="ask-q">NIT ${esc(n.case_id)}${n.ready ? " (ready)" : ""}</div>
    <div class="meta" style="margin:0 0 var(--space-2)">${n.filled} of ${n.total} entries filled, ${n.suggested || 0} suggestions to confirm, ${n.missing || 0} missing.</div>
    <div class="ask-opts">${uiButton("View NIT", {onclick: `openNit('${id}')`})}</div></div>`;
};
function pickOption(btn){
  const input = document.getElementById("dmsg") || document.getElementById("msg");
  if (!input) return;
  if (!btn){ input.placeholder = "Type your answer…"; input.focus(); return; }
  input.value = btn.dataset.v || btn.textContent;
  sendChat(input);
}

const chatTurnCard = t => uiCard(`
  ${msgCopy(t.reply)}
  ${(t.gate||t.graph)?`${stagesRow(t, false)}
    <div class="meta tele" style="margin:0 0 calc(var(--spacing) * 1.5)">${esc((t.gate&&t.gate.reason)||(t.graph&&t.graph.reason)||"")}</div>`:""}
  ${nodesRow(t)}
  ${(t.tools||[]).length?`<div class="tele">${(t.tools||[]).map(toolRow).join("")}</div>`:""}
  <div class="r" style="margin-top:var(--space-2)">${renderMarkdown(t.reply)}</div>
  ${askRow(t)}
  ${nitRow(t)}
  ${teleFooter(t)}`, {cls: "reply"});

// While a turn runs we stream it live: stages light up as the harness reaches
// them, and the reply text appears token by token (with a blinking caret).
// Graph nodes as chips: lit while running, with their measured time once done.
// Several lit at once IS the fan-out, which no amount of "thinking…" conveys.
const nodesRow = m => {
  const names = Object.keys(m.nodes || {});
  if (!names.length) return "";
  return `<div class="cmp-stats" style="margin:0 0 calc(var(--spacing) * 1.5)">` + names.map(n => {
    const s = m.nodes[n];
    const variant = s.status === "running" ? "live" : s.status === "error" ? "bad" : "value";
    const suffix = s.status === "running" ? "" : s.ms != null ? ` ${s.ms}ms` : "";
    return uiBadge(esc(n) + suffix, variant);
  }).join("") + `</div>`;
};

const streamingCard = m => uiCard(`
  ${stagesRow(m, true)}
  ${nodesRow(m)}
  ${m.gate&&m.gate.reason?`<div class="meta" style="margin:0 0 calc(var(--spacing) * 1.5)">${esc(m.gate.reason)}</div>`:""}
  ${(m.tools||[]).map(toolRow).join("")}
  ${m.stream
     ? `<div class="r" style="margin-top:var(--space-2)">${renderMarkdown(m.stream)}<span class="caret"></span></div>`
     : `<div class="meta" style="margin:0">${liveStatus(m)}&hellip;${m.started?` ${Math.round((Date.now()-m.started)/1000)}s`:""}</div>`}`, {cls: "reply"});

// What the turn is really doing right now. "Reasoning" only when the model
// streams its reasoning; otherwise the tool that is running, or the wait.
const liveStatus = m =>
    m.phase === "reasoning" ? "Reasoning"
  : m.phase === "tool" ? toolStatus(m.running)
  : "Waiting for the model";
const toolStatus = name =>
    /^kg_/.test(name || "") ? "Searching past tenders"
  : /^nam_/.test(name || "") ? "Working on the procurement need"
  : `Running ${esc((name || "a tool").replace(/_/g, " "))}`;

// Messages loaded from history (a switched/opened conversation) have no live
// latency/iteration data, and their stored form carries an internal
// "[tools used: ...]" annotation — strip both so the thread reads cleanly.
const stripTools = t => (t || "").replace(/\s*\[tools used:[\s\S]*\]\s*$/, "").trim();
const historicalCard = m => uiCard(`
  ${msgCopy(stripTools(m.reply))}
  <div class="r">${renderMarkdown(stripTools(m.reply))}</div>`, {cls: "reply"});

function renderChatLog(){
  if (!CHAT.length)
    return `<div class="empty" style="padding:calc(var(--spacing) * 1.5) calc(var(--spacing) * 0.5)">Send a message here from any tab. Open Overview to watch it flow through the harness, or the Gateway tab to see every channel's messages together.</div>`;
  return CHAT.map(m => m.role==="user"
      ? `<div class="bubble">${esc(m.text)}</div>`
      : m.pending ? streamingCard(m)
      : m.historical ? historicalCard(m)
      : chatTurnCard(m)).join("");
}

function syncChatLogs(){
  // one conversation, two surfaces: the Chat & watch tab and the side dock
  document.querySelectorAll(".chatlog").forEach(el => {
    el.innerHTML = renderChatLog();
    el.scrollTop = el.scrollHeight;      // dock scrolls its own container
  });
}

// One streamed harness event updates the live card in place.
function applyStreamEvent(pending, ev){
  // Graph events arrive here too when a workflow is called from the chat box.
  // The trace poller animates the chart either way, but it runs every 450ms
  // and stages play on a 620ms stagger — going straight to graphLive() means
  // the Overview panel swaps to the running workflow the moment you hit send.
  if (ev.kind === "graph_start" && typeof graphLive === "function") graphLive(ev.workflow);
  else if (ev.kind === "graph_end" && typeof graphLive === "function") graphLive(null);
  // Graph nodes are not ToolRegistry tools, so none of them ever reached the
  // tool chips — a /gather ran for thirteen seconds showing nothing but
  // "thinking…". Track them separately and render them the same way, because
  // "which four things are happening right now" is the entire point of a wave.
  if (ev.kind === "node_start"){
    (pending.nodes = pending.nodes || {})[ev.node] = {status: "running"};
  } else if (ev.kind === "node_end"){
    (pending.nodes = pending.nodes || {})[ev.node] =
      {status: ev.error ? "error" : "done", ms: ev.ms};
  }
  if (ev.kind === "gate") pending.gate = {decision: ev.decision, reason: ev.reason};
  else if (ev.kind === "route")
    pending.graph = {route: ev.target === "quick_reply" ? "quick" : "full",
                     reason: (pending.graph || {}).reason};
  else if (ev.kind === "triage") (pending.graph = pending.graph || {}).reason = ev.reason;
  else if (ev.kind === "text") pending.stream = (pending.stream || "") + (ev.delta || "");
  else if (ev.kind === "reasoning") pending.phase = "reasoning";
  else if (ev.kind === "tool_start"){ pending.phase = "tool"; pending.running = ev.tool; }
  else if (ev.kind === "ask_options")
    pending.ask = {question: ev.question || "", options: ev.options || []};
  else if (ev.kind === "nit"){ pending.nit = ev; openNit(ev.case_id); }
  else if (ev.kind === "tool"){
    (pending.tools = pending.tools || []).push({
      tool: ev.tool, args: ev.args, output: ev.output,
      status: (ev.output||"").toLowerCase().startsWith("error") ? "error" : "ok",
      summary: (ev.output || "").split(". ")[0].slice(0,120)});
    pending.stream = "";   // a new assistant turn begins after the tool result
    pending.phase = "";    // and waits for the model again
  } else if (ev.kind === "done"){
    pending.pending = false; pending.stream = "";
    if (ev.error) pending.reply = "Error: " + ev.error;
    else Object.assign(pending, ev);   // reply, tools, gate, iterations, latency_ms, consolidation
    if (ev.ask_options && !pending.ask)
      pending.ask = {question: ev.ask_options.question || "", options: ev.ask_options.options || []};
  }
}

async function sendChat(fromInput){
  const input = fromInput || document.getElementById("msg") || document.getElementById("dmsg");
  const text = (input && input.value || "").trim();
  if (!text) return;
  input.value = "";
  CHAT.forEach(m => { if (m.ask) m.ask.answered = true; });   // a question is answered by the next message
  CHAT.push({role:"user", text});
  const pending = {role:"waku", pending:true, stream:"", started: Date.now()};
  CHAT.push(pending);
  syncChatLogs();
  // tick the elapsed counter while we wait for the first token
  const ticker = setInterval(() => { if (pending.pending && !pending.stream) syncChatLogs(); }, 1000);
  try {
    const res = await fetch("/api/chat/stream", {method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:text})});
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;){
      const {value, done} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0){
        const line = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!line.startsWith("data:")) continue;
        try { applyStreamEvent(pending, JSON.parse(line.slice(5).trim())); } catch(e){}
        syncChatLogs();
      }
    }
  } catch(e){ Object.assign(pending, {pending:false, reply:"Error: "+e}); }
  clearInterval(ticker);
  if (pending.pending) pending.pending = false;   // stream ended without a 'done'
  syncChatLogs();
  input.focus();
}
function wireDock(){
  const b = document.getElementById("dsend"), i = document.getElementById("dmsg");
  if (b) b.onclick = () => sendChat(i);
  if (i) i.onkeydown = e => { if (e.key==="Enter") sendChat(i); };
  const close = document.getElementById("dock-close"), reopen = document.getElementById("dock-reopen");
  // Closing the chat also leaves full-page mode and the NIT split: a closed
  // chat that was full left the page and the rail hidden behind nothing, a
  // blank screen.
  const setClosed = v => { document.body.classList.toggle("dock-closed", v);
    if (v){ document.body.classList.remove("dock-full"); closeNit(); }
    localStorage.setItem("dockClosed", v?"1":"0"); };
  if (close) close.onclick = () => setClosed(true);
  if (reopen) reopen.onclick = () => setClosed(false);
  const saved = localStorage.getItem("dockClosed");
  setClosed(saved === null ? window.innerWidth < 1180 : saved === "1");
  syncChatLogs();
}

