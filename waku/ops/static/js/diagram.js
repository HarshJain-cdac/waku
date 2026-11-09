// waku dashboard — the architecture SVG (archSVG, byte-frozen) + its live animation.
// Split out of app.js: classic <script>, shared global scope (no build
// step, no modules). Load order + rules: static/README.md.

// --- Architecture: a calm live SVG that mirrors the whiteboard's structure
// (Harness wraps the ephemeral run · Loop is a cycle · memory feeds up through
// the gate · LLM Ops is a separate loop). Deliberately few arrows + lots of
// air — the detail lives in each tab. Every node is live and clickable.
// DO NOT rewrite this chart. The data-node/data-edge ids each box emits drive
// the live animation via the STAGE map below — keep the two in sync.
function archSVG(d){
  const s = d.stats;
  const box = (x,y,w,h,title,sub,view,cls="",nid="") =>
    `<g class="node ${cls}" ${nid?`data-node="${nid}"`:""} ${view?`onclick="location.hash='${view}'"`:""}>
       <rect class="bx" x="${x}" y="${y}" width="${w}" height="${h}" rx="9"/>
       <text class="nt" x="${x+13}" y="${y+24}">${title}</text>
       ${sub?`<text class="ns" x="${x+13}" y="${y+42}">${sub}</text>`:""}
     </g>`;
  const lbl = (x,y,t) => `<text class="grp" x="${x}" y="${y}">${t}</text>`;
  const flow = (d2,cls="",eid="") => `<path class="flow ${cls}" ${eid?`data-edge="${eid}"`:""} d="${d2}"/>`;
  const flowLbl = (x,y,t,anchor="start") => `<text class="fl" x="${x}" y="${y}" text-anchor="${anchor}">${t}</text>`;

  return `<div style="overflow-x:auto"><svg viewBox="0 -16 1044 680" class="arch" role="img">
    <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" class="head"/></marker></defs>

    <!-- HARNESS container: everything runs on this server (the agent, the NAM
         harness, the offline LLM Ops loop in the tinted sub-panel); the model
         server and the KG are separate services it calls over HTTP.
         knowledge.md describes every box. -->
    <!-- border at y=10 so the arc's label at y=28 sits clear of the dashes -->
    <rect class="container" x="12" y="10" width="1020" height="638" rx="16"/>
    ${lbl(16,-2,"HARNESS — runs on this server · the turn inside is ephemeral")}

    <!-- the turn: gateway → working memory → loop → reply -->
    ${box(28,72,96,56,"Gateway","web · cli · apps","chat","","gateway")}
    ${flow("M124 100 L146 100","","e-gw-intent")}
    <!-- The intent node. No model call — it reads the message and labels the
         turn, which is why it can answer a greeting in milliseconds instead of
         waiting on the inference queue. See waku/tools/intent.py. -->
    ${box(146,72,100,56,"Intent","rules · no LLM","loop","","intent")}
    ${flow("M246 100 L262 100","","e-intent-wm")}
    ${box(262,72,96,56,"Working memory","per turn","memory/overview","","wm")}
    <!-- a greeting never reaches the loop: it turns straight back out -->
    <path class="flow dash" data-edge="e-intent-fast" d="M196 72 C196 54 182 50 156 50 L92 50 C80 50 76 58 76 72"/>
    ${flowLbl(138,46,"greeting → instant reply","middle")}

    <rect class="loopbox" x="370" y="56" width="168" height="166" rx="12"/>
    ${lbl(384,48,"LOOP")}
    ${box(384,72,140,50,"LLM agent","reason","loop","","llm")}
    ${box(384,152,140,52,"Tools","kg_* · nam · notes","tools","","tools")}
    ${flow("M448 122 L448 152")}${flow("M470 152 L470 122")}
    ${flowLbl(456,141,"act")}
    ${flow("M358 100 L370 100","","e-wm-loop")}
    ${flow("M538 100 L558 106")}${flowLbl(542,93,"reply")}
    <!-- MODEL SERVER — the brain is not in this process: every model call
         (the loop, the retrieval gate, NAM's model steps) goes over HTTP to
         the OpenAI-compatible server (waku/loop/models.py is the client). -->
    ${flow("M524 112 C536 130 540 150 552 162","dash","e-llm-model")}
    <g class="node" data-node="model" onclick="location.hash='models'">
      <rect class="bx" x="552" y="150" width="100" height="56" rx="9"/>
      <text class="nt" x="563" y="173">Model server</text>
      <text class="ns" x="563" y="191">over HTTP</text>
    </g>
    ${box(558,84,104,52,"Reply","→ back to you","loop","","reply")}
    <!-- The gateway is the door IN and OUT: the reply leaves through the very
         gateway it arrived at (Telegram sends it, the CLI prints it, voice
         speaks it, the dashboard streams it). A clean over-the-top arc. -->
    <path class="flow" data-edge="e-reply-gw" d="M610 84 C610 40 596 34 566 34 L130 34 C104 34 96 44 96 72" marker-end="url(#arr)"/>
    ${flowLbl(348,28,"reply, out the same gateway","middle")}
    <!-- every turn is saved for consolidation: down a clear right lane,
         then left into the consolidation box -->
    <path class="flow dash" data-edge="e-reply-save" d="M650 136 C660 150 660 200 660 600 L430 600" marker-end="url(#arr)"/>
    ${flowLbl(668,214,"save chats",'start')}

    <!-- KNOWLEDGE GRAPH — a separate read-only service. The five kg_* tools
         reach it over HTTP (waku/nam/kg_tools.py -> the KG's precedent_api on
         :8077 -> NebulaGraph + pgvector), and so do the NAM harness's
         contracts. It lights on the "kg" event the tools emit, so you can SEE
         when a turn consults NRL's tender history. -->
    ${flow("M470 204 C470 240 486 248 520 252","dash","e-tools-kg")}
    ${flowLbl(478,236,"items · tenders · rates · clauses",'start')}
    <g class="node kgbox" data-node="kg" onclick="location.hash='tools'">
      <rect class="bx" x="520" y="226" width="200" height="74" rx="9"/>
      <text class="nt" x="533" y="250">Knowledge graph</text>
      <text class="ns" x="533" y="268">${d.kg && d.kg.ok
        ? d.kg.tenders+" tenders · "+d.kg.price_records+" rates"
        : "not connected"}</text>
      <text class="ns" x="533" y="286">${d.kg && d.kg.ok ? "over HTTP · precedent API" : "start the KG precedent API"}</text>
    </g>

    <!-- retrieval gate feeding working memory (the hero) -->
    <path class="gate node" data-node="gate" onclick="location.hash='memory/overview'" d="M264 250 L340 296 L264 342 L188 296 Z"/>
    <text class="nt" x="264" y="292" text-anchor="middle" style="pointer-events:none">Retrieval gate</text>
    <text class="ns" x="264" y="310" text-anchor="middle" style="pointer-events:none">${s.gate_skips} skip · ${s.gate_retrieves} retrieve</text>
    ${flow("M264 250 L264 128","dash","e-gate-wm")}${flowLbl(274,196,"only if needed")}

    <!-- MEMORY: grouped section with a direct link from the gate to each pillar -->
    ${lbl(40,404,"MEMORY — three pillars")}
    <rect class="memgroup" x="28" y="414" width="600" height="128" rx="12"/>
    ${flow("M148 452 L246 336","dash","e-gate-proc")}
    ${flow("M340 452 L272 344","dash","e-gate-sem")}
    ${flow("M542 452 L286 338","dash","e-gate-epi")}
    ${flowLbl(356,392,"the gate reads all three",'middle')}
    ${box(44,452,208,72,"Procedural","how to act · SKILL.md · "+d.skills.length+" skill(s)","memory/skills","","procedural")}
    ${box(264,452,204,72,"Semantic · FTS5","durable facts · "+d.facts.length+" facts","memory/semantic","","semantic")}
    ${box(480,452,132,72,"Episodic",d.episodes.length+" episodes","memory/episodic","","episodic")}

    <!-- consolidation writes back into memory -->
    ${box(44,576,384,52,"Consolidation · every "+d.consolidate_every+" exchanges",d.chat_pending+"/"+d.consolidate_every*2+" queued → distilled into facts","memory/consolidation","","consolidation")}
    ${flow("M340 576 L340 528","","e-consol-sem")}${flowLbl(350,560,"distill")}

    <!-- NAM HARNESS — the Need Assessment Module as one call (waku/nam,
         POST /api/nam/run from the NAM frontend): router, stage gates S1-S10,
         guardrails, the flow, verification, audit. It is not a chat turn, so
         it sits beside the loop, and reads the KG through its contracts. -->
    <g class="node" data-node="nam">
      <rect class="bx" x="736" y="436" width="280" height="92" rx="9"/>
      <text class="nt" x="750" y="460">NAM harness · /api/nam/run</text>
      <text class="ns" x="750" y="480">router · stages S1–S10 · guardrails · audit</text>
      <text class="ns" x="750" y="498">chat: driver · capture · fill · journey</text>
      <text class="ns" x="750" y="516">from the NAM UI and the chat · reads the KG</text>
    </g>
    <!-- a chat turn about a need is the harness's before it is the model's
         (waku/nam/drive.py): a stated need, an answer, "what next", a value
         to fill. Only what the harness cannot do goes on to the loop. -->
    ${flow("M222 128 C222 170 166 182 166 230 L166 398 L716 398 C730 398 736 410 736 424","dash","e-intent-nam")}
    ${flowLbl(452,392,"need, answer or value → harness first",'start')}
    <!-- up the narrow lane between "save chats" (x 660) and the release
         arrow's head (x 676), so it crosses neither -->
    ${flow("M736 482 C696 482 668 462 668 410 L668 300","dash","e-nam-kg")}

    <!-- LLM OPS: the offline improvement loop — inside the harness (it all
         runs on the laptop) but a distinct tinted sub-panel -->
    <rect class="container ops" x="736" y="40" width="280" height="372" rx="14"/>
    ${lbl(752,64,"LLM OPS — offline improvement loop")}
    ${flowLbl(752,80,"observes each run · improves the agent",'start')}
    <!-- every turn crosses the gap to feed the trace -->
    <path class="flow" data-edge="e-reply-trace" d="M660 104 C700 100 726 100 752 106" marker-end="url(#arr)"/>
    ${flowLbl(688,96,"each turn")}
    ${box(752,92,250,50,"Trace",s.trace_files+" file(s) · always on","ops","","trace")}
    ${flow("M878 142 L878 156")}
    ${box(752,156,250,50,"Eval","deterministic + judge","ops")}
    ${flow("M878 206 L878 220")}
    ${box(752,220,250,50,"Release gate",d.eval_report?"det "+d.eval_report.deterministic+" · judge "+d.eval_report.judge:"run make gate","ops")}
    ${flow("M878 270 L878 284")}
    ${box(752,284,250,50,"Release","new prompt · model · config","ops")}
    <!-- feedback: Release improves the Harness — a short arrow across the gap,
         so the outer loop closes without a long wrap crowding the margins -->
    <path class="flow dash" d="M752 312 C712 324 698 352 676 358" marker-end="url(#arr)"/>
    ${flowLbl(596,346,"improved prompt + config",'end')}
  </svg></div>`;
}

// ---- Live harness animation: light up the diagram as a turn flows through,
// driven by the trace stream so ANY gateway (browser, phone, CLI) triggers it.
// The node/edge ids below MUST match the data-node="…"/data-edge="…" ids that
// archSVG emits above — change one, change the other (that's why both live in
// this file). test_static_assets.py won't catch a mismatch here; the animation
// just silently stops lighting a box.
const STAGE = {
  turn_start:    {nodes:["gateway","wm"],            edges:["e-gw-intent","e-intent-wm"], label:"message in"},
  gate:          {nodes:["gate"],                    edges:["e-gate-wm"],               label:"retrieval gate"},
  llm:           {nodes:["llm","model"],             edges:["e-wm-loop","e-llm-model"], label:"agent reasons"},
  intent:        {nodes:["intent"],                  edges:["e-gw-intent","e-intent-wm"], label:"intent"},
  tool:          {nodes:["tools"],                   edges:[],                          label:"tool runs"},
  kg:            {nodes:["kg","tools"],              edges:["e-tools-kg"],              label:"reading the knowledge graph"},
  nam:           {nodes:["nam"],                     edges:["e-intent-nam","e-nam-kg"], label:"NAM harness: the case's next step"},
  turn_end:      {nodes:["reply","trace"],           edges:["e-reply-trace","e-reply-save"], label:"reply"},
  consolidation: {nodes:["consolidation","semantic"],edges:["e-consol-sem"],            label:"consolidating memory"},
};
let evCursor = null, evQueue = [], playing = false, animating = false;

// A stage's highlight HOLDS until the next stage arrives. That is the whole
// point of a live diagram: "where is this turn right now". The previous
// version cleared every highlight after a fixed 1000ms, so a turn that spent
// twenty seconds waiting on the inference queue flashed the LLM box for one
// second and then sat dark — the stage you most needed to see was the one it
// showed least.
let liveNodes = [], liveEdges = [], turnOpen = false, clearTimer = null;

function paint(sel, cls, on){
  document.querySelectorAll(sel).forEach(el => el.classList.toggle(cls, on));
}
/** Brief flash, for things that genuinely are momentary. */
function hot(sel, cls, ms){
  document.querySelectorAll(sel).forEach(el => {   // every diagram copy lights up
    el.classList.add(cls);
    setTimeout(()=>el.classList.remove(cls), ms);
  });
}
/** Drop the stage we were on, and mark it done on the way out. */
function releaseStage(){
  liveNodes.forEach(n => {
    paint(`[data-node="${n}"]`, "hot", false);
    hot(`[data-node="${n}"]`, "done", 900);
  });
  liveEdges.forEach(e => paint(`[data-edge="${e}"]`, "live", false));
  liveNodes = []; liveEdges = [];
}
function clearAll(){
  releaseStage();
  turnOpen = false;
  document.querySelectorAll(".arch-status").forEach(st => st.innerHTML = "");
}
function status(html){
  document.querySelectorAll(".arch-status").forEach(st =>
    st.innerHTML = `<span class="live-dot"></span>${html}`);
}

function animateStage(ev){
  if (GRAPH_KINDS.has(ev.type)) return animateGraphStage(ev);   // graph.js owns these
  const spec = STAGE[ev.type];
  if (!spec) return;
  // The status line lives in the dock header too, so a turn is followable even
  // when the diagram itself is on another view.
  if (clearTimer){ clearTimeout(clearTimer); clearTimer = null; }

  if (ev.type === "turn_start"){ turnOpen = true; }

  status(spec.label);
  if (!document.querySelector(".arch")){
    // No diagram on screen — the status line is still worth updating, and the
    // held state is meaningless without boxes to hold it on.
    if (ev.type === "turn_end"){ turnOpen = false; clearTimer = setTimeout(clearAll, 1500); }
    return;
  }

  releaseStage();
  liveNodes = spec.nodes.slice();
  liveEdges = spec.edges.slice();
  liveNodes.forEach(n => paint(`[data-node="${n}"]`, "hot", true));
  liveEdges.forEach(e => paint(`[data-edge="${e}"]`, "live", true));

  if (ev.type === "intent"){
    // Say WHICH intent, and light the bypass arc only when the turn really
    // took it — a labelled turn that still ran the loop must not look skipped.
    status(`intent: ${ev.intent}`);
    if (ev.intent === "greeting") hot('[data-edge="e-intent-fast"]', "live", 1600);
    if (ev.intent === "kg" || ev.intent === "nit") paint('[data-node="kg"]', "hot", true);
  }
  if (ev.type === "kg"){
    status(`knowledge graph: ${ev.lane}` + (ev.hits != null ? ` — ${ev.hits} hit(s)` : ""));
  }
  if (ev.type === "tool" && ev.tool){
    status(`tool: ${ev.tool}`);
  }
  if (ev.type === "gate" && ev.decision === "retrieve"){
    ["procedural","semantic","episodic"].forEach(n => {
      liveNodes.push(n); paint(`[data-node="${n}"]`, "hot", true);
    });
    ["e-gate-proc","e-gate-sem","e-gate-epi"].forEach(e => {
      liveEdges.push(e); paint(`[data-edge="${e}"]`, "live", true);
    });
  }
  if (ev.type === "turn_end"){
    turnOpen = false;
    // Hold the finished state briefly so the last stage is readable, then go
    // quiet rather than leaving the diagram lit as if work were still running.
    clearTimer = setTimeout(clearAll, 1800);
  }
}

function playNext(){
  if (!evQueue.length){
    playing = false; animating = false;
    // Do NOT wipe the status mid-turn. An empty queue between polls means the
    // turn is still working — most often waiting on the model — and blanking
    // the diagram there is exactly the moment it should be showing a stage.
    return;
  }
  playing = true; animating = true;
  animateStage(evQueue.shift());
  // Drain fast when several stages arrived together; the HOLD is what makes a
  // stage readable now, not the gap between them.
  setTimeout(playNext, evQueue.length > 3 ? 160 : 420);
}
async function pollEvents(){
  try{
    const r = await (await fetch("/api/events" + (evCursor==null?"":"?cursor="+evCursor))).json();
    if (evCursor != null && r.events.length){
      evQueue.push(...r.events);
      if (!playing) playNext();
    }
    evCursor = r.cursor;
  } catch(e){ /* server busy */ }
}

