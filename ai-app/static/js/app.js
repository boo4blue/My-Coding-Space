/* ── ARIA app.js ──────────────────────────────────────────────────────────── */

const API    = `${location.protocol}//${location.host}`;
const WS_URL = `ws://${location.host}/ws`;

let ws            = null;
let config        = {};
let isStreaming   = false;
let pendingFiles  = [];
let streamEl      = null;   // current streaming message element
let streamText    = '';
let sessionId     = null;
let sessions      = [];

// ── Particle network ─────────────────────────────────────────────────────────

(function particles() {
  const c = document.getElementById('net-canvas');
  const ctx = c.getContext('2d');
  let W, H, pts = [];
  const N = 70;
  const R = (a, b) => a + Math.random() * (b - a);

  const resize = () => { W = c.width = innerWidth; H = c.height = innerHeight; };
  const mkPt   = () => ({ x: R(0,W), y: R(0,H), vx: R(-.18,.18), vy: R(-.18,.18), r: R(.8,2.2), a: R(.2,.7) });

  window.addEventListener('resize', resize);
  resize();
  pts = Array.from({length: N}, mkPt);

  const draw = () => {
    ctx.clearRect(0, 0, W, H);
    for (let i = 0; i < N; i++) {
      for (let j = i+1; j < N; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        const d = Math.hypot(dx, dy);
        if (d < 130) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(124,58,237,${(1-d/130)*.11})`;
          ctx.lineWidth = .5;
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.stroke();
        }
      }
      const p = pts[i];
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
      ctx.fillStyle = `rgba(124,58,237,${p.a})`;
      ctx.fill();
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
    }
    requestAnimationFrame(draw);
  };
  draw();
})();

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.onopen  = () => setStatus('on', 'Connected');
  ws.onclose = () => { setStatus('', 'Reconnecting…'); setTimeout(connectWS, 2500); };
  ws.onerror = () => setStatus('err', 'Connection error');
  ws.onmessage = ({ data }) => {
    let msg; try { msg = JSON.parse(data); } catch { return; }
    onWsMsg(msg);
  };
}

function onWsMsg(msg) {
  switch (msg.type) {

    case 'start':
      hideTyping();
      streamEl   = appendAiMsg('', true);
      streamText = '';
      break;

    case 'chunk':
      if (!streamEl) { streamEl = appendAiMsg('', true); streamText = ''; }
      streamText += msg.text;
      setStreamContent(streamEl, streamText, true);
      scrollBottom();
      break;

    case 'status':
      setTypingLabel(msg.text);
      showTyping(true);
      break;

    case 'tool_call':
      appendToolCall(msg.name, msg.args);
      showTyping(true);
      setTypingLabel(`Running ${msg.name}…`);
      break;

    case 'tool_running':
      setTypingLabel(`Running ${msg.name}…`);
      break;

    case 'tool_result':
      hideTyping();
      appendToolResult(msg.name, msg.result);
      break;

    case 'done':
      if (streamEl) setStreamContent(streamEl, streamText, false);
      streamEl = null; streamText = '';
      setStreaming(false);
      hideTyping();
      scrollBottom();
      loadSessions();
      break;

    case 'error':
      hideTyping();
      setStreaming(false);
      appendAiMsg(`⚠ ${msg.text}`, false);
      break;

    case 'cleared':
      clearChat();
      break;

    case 'session_created':
      sessionId = msg.session_id;
      clearChat();
      loadSessions();
      break;

    case 'session_loaded':
      if (msg.ok) {
        sessionId = msg.session_id;
        clearChat();
        for (const m of msg.messages) {
          if (m.role === 'user')      appendUserMsg(m.content);
          else if (m.role === 'assistant') appendAiMsg(m.content, false);
        }
        loadSessions();
      }
      break;
  }
}

// ── Send ──────────────────────────────────────────────────────────────────────

async function send() {
  if (isStreaming) return;
  const text = qs('#msg-input').value.trim();
  if (!text && pendingFiles.length === 0) return;

  if (pendingFiles.length) {
    await uploadFiles();
  }
  if (!text) return;

  qs('#msg-input').value = '';
  resize_input();
  hideWelcome();
  appendUserMsg(text);
  setStreaming(true);
  showTyping(true);
  setTypingLabel('Thinking…');
  ws.send(JSON.stringify({ type: 'chat', text }));
}

function suggest(btn) {
  const txt = btn.textContent.trim().replace(/^[^\w]+/, '').trim();
  qs('#msg-input').value = txt;
  send();
}

// ── Messages ──────────────────────────────────────────────────────────────────

function appendUserMsg(text) {
  const el = mkMsg('user');
  el.querySelector('.msg-bubble').textContent = text;
  el.querySelector('.msg-copy').onclick = () => copyText(text);
  chatInner().appendChild(el);
  scrollBottom();
  return el;
}

function appendAiMsg(text, streaming = false) {
  const el = mkMsg('ai');
  const bubble = el.querySelector('.msg-bubble');
  if (streaming) bubble.classList.add('streaming');
  if (text) setStreamContent(el, text, streaming);
  el.querySelector('.msg-copy').onclick = () => copyText(el.querySelector('.msg-bubble').dataset.raw || '');
  chatInner().appendChild(el);
  scrollBottom();
  return el;
}

function setStreamContent(msgEl, text, streaming) {
  const bubble = msgEl.querySelector('.msg-bubble');
  bubble.dataset.raw = text;
  bubble.innerHTML = md(text);
  addCopyBtns(bubble);
  if (streaming) bubble.classList.add('streaming');
  else           bubble.classList.remove('streaming');
}

function mkMsg(role) {
  const aiName = config.ai_name || 'ARIA';
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const av = role === 'user' ? 'U' : '✦';
  div.innerHTML = `
    <div class="msg-av">${av}</div>
    <div class="msg-col">
      <div class="msg-bubble"></div>
      <div class="msg-meta">
        <span>${role === 'ai' ? aiName + ' · ' : ''}${now()}</span>
        <button class="msg-copy" title="Copy">⎘ copy</button>
      </div>
    </div>`;
  return div;
}

function appendToolCall(name, args) {
  const el = document.createElement('div');
  el.className = 'tool-call';
  const argsStr = Object.entries(args || {})
    .map(([k, v]) => `${k}: ${JSON.stringify(v).slice(0, 50)}`)
    .join(', ');
  el.innerHTML = `<span class="spin">⚙</span> <strong>${esc(name)}</strong><span style="color:var(--text3);margin-left:6px;font-size:11px">${esc(argsStr)}</span>`;
  chatInner().appendChild(el);
  scrollBottom();
}

function appendToolResult(name, result) {
  const el = document.createElement('div');
  el.className = 'tool-result';
  el.innerHTML = `
    <div class="tool-result-head" onclick="this.parentElement.classList.toggle('open')">
      <span>✓ ${esc(name)}</span>
      <span><span class="chevron">▶</span></span>
    </div>
    <div class="tool-result-body">${esc(result)}</div>`;
  chatInner().appendChild(el);
  scrollBottom();
}

function addCopyBtns(bubble) {
  bubble.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.code-copy')) return;
    const lang = pre.querySelector('code')?.className?.replace('language-','') || 'code';
    const hdr = document.createElement('div');
    hdr.className = 'code-header';
    const btn = document.createElement('button');
    btn.className = 'code-copy';
    btn.textContent = 'Copy';
    btn.onclick = () => {
      copyText(pre.querySelector('code')?.textContent || pre.textContent);
      btn.textContent = '✓ Copied';
      setTimeout(() => btn.textContent = 'Copy', 1600);
    };
    hdr.appendChild(document.createTextNode(lang));
    hdr.appendChild(btn);
    pre.insertBefore(hdr, pre.firstChild);
  });
}

// ── Markdown ──────────────────────────────────────────────────────────────────

function md(text) {
  let h = text;

  // Fenced code blocks
  h = h.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="language-${lang||'text'}">${esc(code.trimEnd())}</code></pre>`);

  // Inline code
  h = h.replace(/`([^`\n]+)`/g, (_, c) => `<code>${esc(c)}</code>`);

  // Headings
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm,   '<h1>$1</h1>');

  // Bold / italic
  h = h.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Blockquote
  h = h.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // HR
  h = h.replace(/^---$/gm, '<hr>');

  // Lists
  h = h.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  h = h.replace(/(<li>.*<\/li>\n?)+/g, s => `<ul>${s}</ul>`);
  h = h.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Links
  h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Tables
  h = h.replace(/\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)+)/g, (_, header, rows) => {
    const ths = header.split('|').filter(s=>s.trim()).map(h=>`<th>${h.trim()}</th>`).join('');
    const trs = rows.trim().split('\n').map(row => {
      const tds = row.split('|').filter(s=>s.trim()).map(c=>`<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });

  // Paragraphs
  const lines = h.split('\n');
  const out = []; let para = [];
  for (const line of lines) {
    const block = /^<(h[1-6]|ul|ol|li|pre|blockquote|hr|table|thead|tbody|tr)/.test(line.trim());
    if (block) { if (para.length) { out.push(`<p>${para.join(' ')}</p>`); para=[]; } out.push(line); }
    else if (!line.trim()) { if (para.length) { out.push(`<p>${para.join(' ')}</p>`); para=[]; } }
    else para.push(line);
  }
  if (para.length) out.push(`<p>${para.join(' ')}</p>`);
  return out.join('\n');
}

// ── UI helpers ────────────────────────────────────────────────────────────────

const qs  = s => document.querySelector(s);
const qsa = s => document.querySelectorAll(s);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

function chatInner()   { return qs('#chat-inner'); }
function scrollBottom() { const el=qs('#chat-scroll'); el.scrollTop=el.scrollHeight; }
function now()         { return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}); }

function hideWelcome() { qs('#welcome').classList.add('gone'); }

function clearChat() {
  chatInner().querySelectorAll('.msg,.tool-call,.tool-result').forEach(e=>e.remove());
  qs('#welcome').classList.remove('gone');
  streamEl=null; streamText='';
}

function showTyping(show)    { qs('#typing-wrap').classList.toggle('hidden', !show); if(show) scrollBottom(); }
function hideTyping()        { qs('#typing-wrap').classList.add('hidden'); }
function setTypingLabel(txt) { qs('#t-label').textContent = txt; }

function setStreaming(v) {
  isStreaming = v;
  qs('#send-btn').disabled = v;
  qs('#msg-input').disabled = v;
}

function setStatus(state, label) {
  const pip = qs('#status-pip');
  pip.className = 'status-pip' + (state ? ` ${state}` : '');
  qs('#status-label').textContent = label;
}

function copyText(txt) {
  navigator.clipboard.writeText(txt).catch(()=>{});
  toast('Copied!');
}

function toast(msg, type='') {
  const c = qs('#toasts');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(()=>el.remove(), 3200);
}

function resize_input() {
  const t = qs('#msg-input');
  t.style.height='auto';
  t.style.height = Math.min(t.scrollHeight,180)+'px';
}

// ── Status / models ───────────────────────────────────────────────────────────

async function loadStatus() {
  try {
    const r = await fetch(`${API}/api/status`);
    const d = await r.json();
    config = d;

    const name = d.ai_name || 'ARIA';
    qs('#brand-name').textContent  = name;
    qs('#w-name').textContent      = name;
    document.title                  = name;
    qs('#model-info-meta').textContent = d.model_name || '';

    const sel = qs('#model-select');
    sel.innerHTML = '';
    const files = d.model_files?.length ? d.model_files : (d.model_name ? [d.model_name] : ['No model found']);
    for (const f of files) {
      const o = document.createElement('option');
      o.value = o.textContent = f;
      if (d.model_name && f === d.model_name) o.selected = true;
      sel.appendChild(o);
    }

    if (!d.model_exists) {
      setStatus('err', 'No model — run download_model.py');
      toast('No model file found. Run: python download_model.py', 'err');
    } else if (d.ready) {
      setStatus('on', `${d.model_name} loaded`);
    } else {
      setStatus('on', `${d.model_name} — ready`);
    }
  } catch(e) {
    setStatus('err', 'Server error');
  }
}

qs('#model-select').addEventListener('change', async e => {
  const f = e.target.value;
  if (!f || f.includes('No model')) return;
  await fetch(`${API}/api/config`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ model_path: `models/${f}` }),
  });
  toast(`Switched to ${f}`, 'ok');
  qs('#model-info-meta').textContent = f;
});

// ── Sessions ──────────────────────────────────────────────────────────────────

async function loadSessions() {
  try {
    const r = await fetch(`${API}/api/sessions`);
    sessions = await r.json();
    renderSessions(sessions);
  } catch(e) {}
}

function renderSessions(list) {
  const el = qs('#sessions-list');
  el.innerHTML = '';
  for (const s of list) {
    const item = document.createElement('div');
    item.className = 'sess-item' + (s.id === sessionId ? ' active' : '');
    item.innerHTML = `
      <span class="s-icon">💬</span>
      <span class="s-title" title="${esc(s.title)}">${esc(s.title)}</span>
      <button class="sess-del" data-id="${s.id}" title="Delete">✕</button>`;
    item.addEventListener('click', ev => {
      if (ev.target.classList.contains('sess-del')) {
        delSession(ev.target.dataset.id);
      } else {
        ws.send(JSON.stringify({ type:'load_session', session_id: s.id }));
      }
    });
    el.appendChild(item);
  }
}

async function delSession(id) {
  await fetch(`${API}/api/session/${id}`, { method:'DELETE' });
  if (id === sessionId) { clearChat(); sessionId=null; }
  loadSessions();
}

qs('#session-search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  renderSessions(sessions.filter(s => s.title.toLowerCase().includes(q)));
});

qs('#new-chat-btn').addEventListener('click', () => {
  ws.send(JSON.stringify({ type:'new_session' }));
});

// ── Knowledge ─────────────────────────────────────────────────────────────────

async function loadKB() {
  try {
    const r = await fetch(`${API}/api/knowledge`);
    const docs = await r.json();
    const el = qs('#kb-docs');
    el.innerHTML = '';
    if (!docs.length) { el.innerHTML = '<div style="font-size:12px;color:var(--text3);padding:4px">No documents yet. Add files above.</div>'; return; }
    for (const d of docs) {
      const item = document.createElement('div');
      item.className = 'kb-item';
      item.innerHTML = `
        <span class="kb-name" title="${esc(d.source)}">${esc(d.source)}</span>
        <span class="kb-chunks">${d.chunks} chunks</span>
        <button class="kb-del" data-src="${esc(d.source)}">✕</button>`;
      item.querySelector('.kb-del').onclick = async () => {
        await fetch(`${API}/api/knowledge/${encodeURIComponent(d.source)}`, { method:'DELETE' });
        loadKB();
      };
      el.appendChild(item);
    }
  } catch(e) {}
}

qs('#kb-file-input').addEventListener('change', async e => {
  for (const f of e.target.files) await uploadToKB(f);
  e.target.value='';
  loadKB();
  toast('Files added to knowledge base ✓', 'ok');
});

async function uploadToKB(file) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('add_to_kb', 'true');
  await fetch(`${API}/api/upload`, { method:'POST', body: fd });
}

// ── File attachments ──────────────────────────────────────────────────────────

qs('#file-input').addEventListener('change', e => {
  for (const f of e.target.files) pendingFiles.push(f);
  e.target.value='';
  renderAttach();
});

function renderAttach() {
  const bar = qs('#attach-strip');
  bar.innerHTML='';
  if (!pendingFiles.length) { bar.classList.add('hidden'); return; }
  bar.classList.remove('hidden');
  pendingFiles.forEach((f, i) => {
    const chip = document.createElement('div');
    chip.className='attach-chip';
    chip.innerHTML=`📎 ${esc(f.name)} <button class="attach-x" data-i="${i}">✕</button>`;
    chip.querySelector('.attach-x').onclick = () => { pendingFiles.splice(i,1); renderAttach(); };
    bar.appendChild(chip);
  });
}

async function uploadFiles() {
  for (const f of pendingFiles) await uploadToKB(f);
  toast(`${pendingFiles.length} file(s) added to knowledge base ✓`, 'ok');
  pendingFiles=[];
  renderAttach();
}

// ── Drag & drop ───────────────────────────────────────────────────────────────

let dragN = 0;
document.addEventListener('dragenter', () => { dragN++; qs('#drop-overlay').classList.add('show'); });
document.addEventListener('dragleave', () => { if(--dragN===0) qs('#drop-overlay').classList.remove('show'); });
document.addEventListener('dragover',  e => e.preventDefault());
document.addEventListener('drop', async e => {
  e.preventDefault(); dragN=0; qs('#drop-overlay').classList.remove('show');
  for (const f of e.dataTransfer.files) await uploadToKB(f);
  loadKB();
  toast(`Files added ✓`, 'ok');
});

// ── Input ─────────────────────────────────────────────────────────────────────

qs('#msg-input').addEventListener('keydown', e => {
  if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
qs('#msg-input').addEventListener('input', resize_input);
qs('#send-btn').addEventListener('click', send);
qs('#clear-btn').addEventListener('click', () => {
  ws.send(JSON.stringify({ type:'clear' }));
});

// ── Sidebar ───────────────────────────────────────────────────────────────────

qs('#sidebar-toggle').addEventListener('click', () => qs('#sidebar').classList.toggle('open'));
qs('#collapse-btn').addEventListener('click', () => qs('#sidebar').classList.toggle('collapsed'));

// ── Slide panels ──────────────────────────────────────────────────────────────

function openPanel(name) {
  qsa('.slide-panel').forEach(p => p.classList.remove('open'));
  qs(`#panel-${name}`)?.classList.add('open');
  qs('#panel-backdrop').classList.add('show');
  if (name==='knowledge') loadKB();
  if (name==='settings')  loadSettings();
  qsa('.foot-btn').forEach(b => b.classList.toggle('active', b.dataset.panel===name));
}
function closePanel(name) {
  qs(`#panel-${name}`)?.classList.remove('open');
  qs('#panel-backdrop').classList.remove('show');
  qsa('.foot-btn').forEach(b => b.classList.remove('active'));
}

qsa('.foot-btn').forEach(b => {
  b.addEventListener('click', () => {
    const name = b.dataset.panel;
    const panel = qs(`#panel-${name}`);
    if (panel?.classList.contains('open')) closePanel(name);
    else openPanel(name);
  });
});

qsa('.panel-close').forEach(btn => {
  btn.addEventListener('click', () => closePanel(btn.dataset.panel));
});

qs('#panel-backdrop').addEventListener('click', () => {
  qsa('.slide-panel.open').forEach(p => closePanel(p.id.replace('panel-','')));
});

// ── Settings ──────────────────────────────────────────────────────────────────

async function loadSettings() {
  try {
    const r = await fetch(`${API}/api/config`);
    const c = await r.json();
    qs('#s-name').value       = c.ai_name || '';
    qs('#s-personality').value = c.ai_personality || '';
    qs('#s-model-path').value = c.model_path || '';
    qs('#s-nctx').value       = c.n_ctx ?? 4096;
    qs('#s-gpu').value        = c.n_gpu_layers ?? 0;
    qs('#s-temp').value       = c.temperature ?? 0.7;
    qs('#s-workspace').value  = c.workspace_path || '';
    qs('#s-shell').checked    = c.enable_shell !== false;
    qs('#s-guard').checked    = c.shell_confirm_dangerous !== false;
  } catch(e) {}
}

qs('#save-settings').addEventListener('click', async () => {
  const body = {
    ai_name:               qs('#s-name').value,
    ai_personality:        qs('#s-personality').value,
    model_path:            qs('#s-model-path').value,
    n_ctx:                 parseInt(qs('#s-nctx').value)||4096,
    n_gpu_layers:          parseInt(qs('#s-gpu').value)??0,
    temperature:           parseFloat(qs('#s-temp').value)||.7,
    workspace_path:        qs('#s-workspace').value,
    enable_shell:          qs('#s-shell').checked,
    shell_confirm_dangerous: qs('#s-guard').checked,
  };
  try {
    const r = await fetch(`${API}/api/config`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    config = await r.json();
    qs('#brand-name').textContent = config.ai_name||'ARIA';
    qs('#w-name').textContent     = config.ai_name||'ARIA';
    document.title = config.ai_name||'ARIA';
    toast('Settings saved ✓', 'ok');
    closePanel('settings');
  } catch(e) { toast('Failed to save', 'err'); }
});

// ── Init ──────────────────────────────────────────────────────────────────────

(async function init() {
  await loadStatus();
  connectWS();
  loadSessions();
})();
