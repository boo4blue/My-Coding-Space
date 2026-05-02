/* ── ARIA Frontend ─────────────────────────────────────────────────────── */

const WS_URL = `ws://${location.host}/ws`;
const API    = `${location.protocol}//${location.host}`;

let ws = null;
let currentModel = '';
let isStreaming = false;
let config = {};
let pendingFiles = [];
let currentStreamEl = null;
let currentStreamText = '';
let sessionId = null;

// ── Particle Background ────────────────────────────────────────────────────

(function initParticles() {
  const canvas = document.getElementById('bg-canvas');
  const ctx = canvas.getContext('2d');
  let W, H, particles = [];
  const N = 80;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function rand(a, b) { return a + Math.random() * (b - a); }

  function createParticle() {
    return {
      x: rand(0, W), y: rand(0, H),
      vx: rand(-0.15, 0.15), vy: rand(-0.15, 0.15),
      r: rand(1, 2.5),
      alpha: rand(0.2, 0.7),
    };
  }

  function init() {
    resize();
    particles = Array.from({ length: N }, createParticle);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // Draw connections
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 140) {
          const alpha = (1 - dist / 140) * 0.12;
          ctx.beginPath();
          ctx.strokeStyle = `rgba(124,58,237,${alpha})`;
          ctx.lineWidth = 0.5;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    // Draw particles
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(124,58,237,${p.alpha})`;
      ctx.fill();

      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W;
      if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H;
      if (p.y > H) p.y = 0;
    }

    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  init();
  draw();
})();

// ── WebSocket ──────────────────────────────────────────────────────────────

function connectWS() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setStatus('online', 'Connected');
    ws.send(JSON.stringify({ type: 'ping' }));
  };

  ws.onclose = () => {
    setStatus('offline', 'Disconnected');
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => {
    setStatus('offline', 'Error');
  };

  ws.onmessage = ({ data }) => {
    let msg;
    try { msg = JSON.parse(data); } catch { return; }
    handleWsMessage(msg);
  };
}

function handleWsMessage(msg) {
  switch (msg.type) {

    case 'start':
      showTyping(false);
      currentStreamEl = appendAiMessage('');
      currentStreamText = '';
      break;

    case 'chunk':
      if (!currentStreamEl) {
        currentStreamEl = appendAiMessage('');
        currentStreamText = '';
      }
      currentStreamText += msg.text;
      renderStreamChunk(currentStreamEl, currentStreamText, true);
      scrollToBottom();
      break;

    case 'tool_call':
      appendToolCall(msg.name, msg.args);
      setTypingLabel(`Using ${msg.name}…`);
      showTyping(true);
      break;

    case 'tool_running':
      setTypingLabel(`Running ${msg.name}…`);
      break;

    case 'tool_result':
      showTyping(false);
      appendToolResult(msg.name, msg.result);
      break;

    case 'done':
      if (currentStreamEl) {
        renderStreamChunk(currentStreamEl, currentStreamText, false);
      }
      currentStreamEl = null;
      currentStreamText = '';
      setStreaming(false);
      showTyping(false);
      scrollToBottom();
      refreshSessions();
      break;

    case 'error':
      showTyping(false);
      setStreaming(false);
      appendAiMessage(`⚠ ${msg.text}`);
      break;

    case 'cleared':
      clearChat();
      break;

    case 'session_created':
      sessionId = msg.session_id;
      clearChat();
      refreshSessions();
      break;

    case 'session_loaded':
      if (msg.ok) {
        sessionId = msg.session_id;
        clearChat();
        for (const m of msg.messages) {
          if (m.role === 'user') appendUserMessage(m.content);
          else if (m.role === 'assistant') appendAiMessage(m.content, false);
        }
        refreshSessions();
      }
      break;
  }
}

// ── Sending messages ───────────────────────────────────────────────────────

function sendMessage() {
  if (isStreaming) return;
  const input = document.getElementById('msg-input');
  const text  = input.value.trim();
  if (!text && pendingFiles.length === 0) return;

  // Handle file uploads first
  if (pendingFiles.length > 0) {
    uploadPendingFiles().then(() => {
      if (text) doSend(text);
    });
    return;
  }

  doSend(text);
  input.value = '';
  autoResize();
}

function doSend(text) {
  hideWelcome();
  appendUserMessage(text);
  setStreaming(true);
  showTyping(true);
  setTypingLabel('Thinking…');

  ws.send(JSON.stringify({
    type: 'chat',
    text,
    model: currentModel,
  }));
}

function sendSuggestion(btn) {
  const text = btn.querySelector('.icon').nextSibling.textContent.trim();
  document.getElementById('msg-input').value = text;
  sendMessage();
}

// ── Message rendering ──────────────────────────────────────────────────────

function appendUserMessage(text) {
  const wrap = document.createElement('div');
  wrap.className = 'message user';
  wrap.innerHTML = `
    <div class="msg-avatar">U</div>
    <div class="msg-body">
      <div class="msg-bubble">${escapeHtml(text)}</div>
      <div class="msg-time">${timeStr()}</div>
    </div>`;
  chatInner().appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function appendAiMessage(text, stream = true) {
  const aiName = config.ai_name || 'ARIA';
  const wrap = document.createElement('div');
  wrap.className = 'message ai';
  wrap.innerHTML = `
    <div class="msg-avatar">✦</div>
    <div class="msg-body">
      <div class="msg-bubble ${stream ? 'cursor' : ''}" data-raw=""></div>
      <div class="msg-time">${aiName} · ${timeStr()}</div>
    </div>`;
  chatInner().appendChild(wrap);
  if (text) {
    renderStreamChunk(wrap, text, stream);
  }
  scrollToBottom();
  return wrap;
}

function renderStreamChunk(wrap, text, streaming) {
  const bubble = wrap.querySelector('.msg-bubble');
  bubble.dataset.raw = text;
  bubble.innerHTML = parseMarkdown(text);
  if (streaming) {
    bubble.classList.add('cursor');
    addCodeCopyButtons(bubble);
  } else {
    bubble.classList.remove('cursor');
    addCodeCopyButtons(bubble);
  }
}

function appendToolCall(name, args) {
  const el = document.createElement('div');
  el.className = 'tool-call-block';
  const argsStr = Object.entries(args || {}).map(([k, v]) => `${k}: ${JSON.stringify(v).slice(0, 60)}`).join(', ');
  el.innerHTML = `<span class="spin">⚙</span> <strong>${name}</strong> <span style="color:var(--text-muted);font-size:11px;">${argsStr}</span>`;
  el.id = `tc-${name}-${Date.now()}`;
  chatInner().appendChild(el);
  scrollToBottom();
}

function appendToolResult(name, result) {
  const el = document.createElement('div');
  el.className = 'tool-result-block';
  const preview = result.slice(0, 120).replace(/</g, '&lt;') + (result.length > 120 ? '…' : '');
  el.innerHTML = `
    <div class="tool-result-header" onclick="this.parentElement.classList.toggle('expanded')">
      <span>✓ ${name} result</span>
      <span>▸ expand</span>
    </div>
    <div class="tool-result-body">${escapeHtml(result)}</div>`;
  chatInner().appendChild(el);
  scrollToBottom();
}

function addCodeCopyButtons(bubble) {
  bubble.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.code-copy-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'code-copy-btn';
    btn.textContent = 'Copy';
    btn.onclick = () => {
      const code = pre.querySelector('code')?.textContent || pre.textContent;
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = '✓ Copied';
        setTimeout(() => btn.textContent = 'Copy', 1500);
      });
    };
    pre.style.position = 'relative';
    pre.appendChild(btn);
  });
}

// ── Markdown parser (lightweight) ─────────────────────────────────────────

function parseMarkdown(text) {
  // Escape HTML first (but preserve what we build)
  let html = text;

  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = code.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<pre><code class="language-${lang || 'text'}">${escaped}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`\n]+)`/g, (_, c) => `<code>${c.replace(/</g,'&lt;')}</code>`);

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/_(.+?)_/g, '<em>$1</em>');

  // Blockquote
  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr>');

  // Unordered list
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, s => `<ul>${s}</ul>`);

  // Ordered list
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Links
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Tables (simple)
  html = html.replace(/\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)+)/g, (_, header, rows) => {
    const ths = header.split('|').filter(s => s.trim()).map(h => `<th>${h.trim()}</th>`).join('');
    const trs = rows.trim().split('\n').map(row => {
      const tds = row.split('|').filter(s => s.trim()).map(c => `<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });

  // Paragraphs — wrap consecutive non-html lines
  const lines = html.split('\n');
  const result = [];
  let para = [];

  for (const line of lines) {
    const isBlock = /^<(h[1-6]|ul|ol|li|pre|blockquote|hr|table|thead|tbody|tr)/.test(line.trim());
    if (isBlock) {
      if (para.length) { result.push(`<p>${para.join(' ')}</p>`); para = []; }
      result.push(line);
    } else if (line.trim() === '') {
      if (para.length) { result.push(`<p>${para.join(' ')}</p>`); para = []; }
    } else {
      para.push(line);
    }
  }
  if (para.length) result.push(`<p>${para.join(' ')}</p>`);

  return result.join('\n');
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── UI helpers ─────────────────────────────────────────────────────────────

function chatInner() { return document.getElementById('chat-inner'); }
function scrollToBottom() {
  const chat = document.getElementById('chat');
  chat.scrollTop = chat.scrollHeight;
}

function hideWelcome() {
  document.getElementById('welcome').classList.add('hidden');
}

function clearChat() {
  const inner = chatInner();
  // Remove all messages but keep welcome
  inner.querySelectorAll('.message, .tool-call-block, .tool-result-block').forEach(el => el.remove());
  document.getElementById('welcome').classList.remove('hidden');
  currentStreamEl = null;
  currentStreamText = '';
}

function showTyping(show, label = '') {
  const el = document.getElementById('typing-indicator');
  el.classList.toggle('visible', show);
  if (label) setTypingLabel(label);
  if (show) scrollToBottom();
}

function setTypingLabel(text) {
  document.getElementById('typing-label').textContent = text;
}

function setStreaming(val) {
  isStreaming = val;
  document.getElementById('send-btn').disabled = val;
  document.getElementById('msg-input').disabled = val;
}

function setStatus(state, text) {
  document.getElementById('status-dot').className = `status-dot ${state}`;
  document.getElementById('status-text').textContent = text;
}

function timeStr() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Model selector ─────────────────────────────────────────────────────────

async function loadStatus() {
  try {
    const res = await fetch(`${API}/api/status`);
    const data = await res.json();
    config = data;

    currentModel = data.current_model || data.models[0] || 'llama3.2';

    const sel = document.getElementById('model-select');
    sel.innerHTML = '';
    if (data.models.length === 0) {
      sel.innerHTML = '<option>No models found</option>';
    } else {
      for (const m of data.models) {
        const opt = document.createElement('option');
        opt.value = opt.textContent = m;
        if (m === currentModel) opt.selected = true;
        sel.appendChild(opt);
      }
    }

    const aiName = data.ai_name || 'ARIA';
    document.getElementById('ai-name-logo').textContent = aiName;
    document.getElementById('ai-name-welcome').textContent = aiName;
    document.title = `${aiName} — Local AI`;

    if (data.ollama) {
      setStatus('online', `${data.models.length} model${data.models.length !== 1 ? 's' : ''} ready`);
    } else {
      setStatus('offline', 'Ollama not running');
      toast('Ollama is not running. Run: ollama serve', 'error');
    }
  } catch (e) {
    setStatus('offline', 'Server error');
  }
}

document.getElementById('model-select').addEventListener('change', e => {
  currentModel = e.target.value;
});

// ── Sessions ───────────────────────────────────────────────────────────────

async function refreshSessions() {
  try {
    const res = await fetch(`${API}/api/sessions`);
    const sessions = await res.json();
    const list = document.getElementById('sessions-list');
    list.innerHTML = '';
    for (const s of sessions) {
      const el = document.createElement('div');
      el.className = `session-item${s.id === sessionId ? ' active' : ''}`;
      el.innerHTML = `
        <span class="title" title="${escapeHtml(s.title)}">${escapeHtml(s.title)}</span>
        <button class="del-btn" data-id="${s.id}">✕</button>`;
      el.addEventListener('click', (e) => {
        if (e.target.classList.contains('del-btn')) {
          deleteSession(e.target.dataset.id);
        } else {
          loadSession(s.id);
        }
      });
      list.appendChild(el);
    }
  } catch(e) {}
}

function loadSession(id) {
  ws.send(JSON.stringify({ type: 'load_session', session_id: id }));
}

async function deleteSession(id) {
  await fetch(`${API}/api/session/${id}`, { method: 'DELETE' });
  if (id === sessionId) { clearChat(); sessionId = null; }
  refreshSessions();
}

document.getElementById('new-chat-btn').addEventListener('click', () => {
  ws.send(JSON.stringify({ type: 'new_session' }));
});

// ── Knowledge base ─────────────────────────────────────────────────────────

async function refreshKB() {
  try {
    const res = await fetch(`${API}/api/knowledge`);
    const docs = await res.json();
    const list = document.getElementById('kb-docs-list');
    list.innerHTML = '';
    if (docs.length === 0) {
      list.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:4px;">No documents yet. Drop files here or use the + Add file button.</div>';
      return;
    }
    for (const d of docs) {
      const el = document.createElement('div');
      el.className = 'kb-doc';
      el.innerHTML = `
        <span class="name">${escapeHtml(d.source)}</span>
        <span class="chunks">${d.chunks} chunks</span>
        <button class="del" data-src="${escapeHtml(d.source)}">✕</button>`;
      el.querySelector('.del').addEventListener('click', async (e) => {
        await fetch(`${API}/api/knowledge/${encodeURIComponent(d.source)}`, { method: 'DELETE' });
        refreshKB();
      });
      list.appendChild(el);
    }
  } catch(e) {}
}

document.getElementById('kb-file-input').addEventListener('change', async (e) => {
  for (const file of e.target.files) {
    await uploadToKB(file);
  }
  e.target.value = '';
  refreshKB();
  toast('Files added to knowledge base ✓', 'success');
});

async function uploadToKB(file) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('add_to_kb', 'true');
  await fetch(`${API}/api/upload`, { method: 'POST', body: fd });
}

// ── File attachments ───────────────────────────────────────────────────────

document.getElementById('file-input').addEventListener('change', (e) => {
  for (const f of e.target.files) addPendingFile(f);
  e.target.value = '';
});

function addPendingFile(file) {
  pendingFiles.push(file);
  renderAttachments();
}

function renderAttachments() {
  const bar = document.getElementById('attachments-bar');
  bar.innerHTML = '';
  for (let i = 0; i < pendingFiles.length; i++) {
    const chip = document.createElement('div');
    chip.className = 'attachment-chip';
    chip.innerHTML = `📎 ${escapeHtml(pendingFiles[i].name)} <span class="remove" data-i="${i}">✕</span>`;
    chip.querySelector('.remove').addEventListener('click', () => {
      pendingFiles.splice(i, 1);
      renderAttachments();
    });
    bar.appendChild(chip);
  }
}

async function uploadPendingFiles() {
  const msg = [];
  for (const file of pendingFiles) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('add_to_kb', 'true');
    try {
      const res = await fetch(`${API}/api/upload`, { method: 'POST', body: fd });
      const data = await res.json();
      msg.push(`Uploaded "${data.filename}" → added to knowledge base`);
    } catch (e) {
      msg.push(`Failed to upload "${file.name}"`);
    }
  }
  pendingFiles = [];
  renderAttachments();
  if (msg.length) toast(msg.join('; '), 'success');
}

// ── Drag and drop ──────────────────────────────────────────────────────────

let dragCounter = 0;

document.addEventListener('dragenter', (e) => {
  dragCounter++;
  document.getElementById('drop-overlay').classList.add('active');
});

document.addEventListener('dragleave', (e) => {
  dragCounter--;
  if (dragCounter === 0) {
    document.getElementById('drop-overlay').classList.remove('active');
  }
});

document.addEventListener('dragover', (e) => e.preventDefault());

document.addEventListener('drop', async (e) => {
  e.preventDefault();
  dragCounter = 0;
  document.getElementById('drop-overlay').classList.remove('active');
  const files = [...e.dataTransfer.files];
  for (const f of files) await uploadToKB(f);
  refreshKB();
  if (files.length) toast(`${files.length} file(s) added to knowledge base ✓`, 'success');
});

// ── Input ──────────────────────────────────────────────────────────────────

const msgInput = document.getElementById('msg-input');

msgInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

msgInput.addEventListener('input', () => {
  autoResize();
  const len = msgInput.value.length;
  document.getElementById('char-count').textContent = len > 100 ? `${len} chars` : '';
});

function autoResize() {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 180) + 'px';
}

document.getElementById('send-btn').addEventListener('click', sendMessage);

// ── Clear ──────────────────────────────────────────────────────────────────

document.getElementById('clear-btn').addEventListener('click', () => {
  ws.send(JSON.stringify({ type: 'clear' }));
  clearChat();
});

// ── Settings ───────────────────────────────────────────────────────────────

document.getElementById('settings-btn').addEventListener('click', openSettings);
document.getElementById('settings-close').addEventListener('click', closeSettings);
document.getElementById('settings-modal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeSettings();
});

async function openSettings() {
  try {
    const res = await fetch(`${API}/api/config`);
    const cfg = await res.json();
    document.getElementById('cfg-name').value = cfg.ai_name || '';
    document.getElementById('cfg-personality').value = cfg.ai_personality || '';
    document.getElementById('cfg-ollama-url').value = cfg.ollama_url || '';
    document.getElementById('cfg-default-model').value = cfg.default_model || '';
    document.getElementById('cfg-workspace').value = cfg.workspace_path || '';
    document.getElementById('cfg-enable-shell').checked = cfg.enable_shell !== false;
    document.getElementById('cfg-shell-confirm').checked = cfg.shell_confirm_dangerous !== false;
  } catch(e) {}
  document.getElementById('settings-modal').classList.add('open');
}

function closeSettings() {
  document.getElementById('settings-modal').classList.remove('open');
}

document.getElementById('settings-save').addEventListener('click', async () => {
  const newCfg = {
    ai_name: document.getElementById('cfg-name').value,
    ai_personality: document.getElementById('cfg-personality').value,
    ollama_url: document.getElementById('cfg-ollama-url').value,
    default_model: document.getElementById('cfg-default-model').value,
    workspace_path: document.getElementById('cfg-workspace').value,
    enable_shell: document.getElementById('cfg-enable-shell').checked,
    shell_confirm_dangerous: document.getElementById('cfg-shell-confirm').checked,
  };
  try {
    const res = await fetch(`${API}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newCfg),
    });
    config = await res.json();
    document.getElementById('ai-name-logo').textContent = config.ai_name || 'ARIA';
    document.getElementById('ai-name-welcome').textContent = config.ai_name || 'ARIA';
    document.title = `${config.ai_name || 'ARIA'} — Local AI`;
    toast('Settings saved ✓', 'success');
    closeSettings();
  } catch(e) {
    toast('Failed to save settings', 'error');
  }
});

// ── Sidebar ────────────────────────────────────────────────────────────────

document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
});

document.querySelectorAll('.sidebar-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const name = tab.dataset.tab;
    document.querySelectorAll('.sidebar-panel').forEach(p => p.classList.remove('visible'));
    if (name === 'knowledge') {
      document.getElementById('panel-knowledge').classList.add('visible');
      refreshKB();
    }
  });
});

// ── Init ───────────────────────────────────────────────────────────────────

(async function init() {
  await loadStatus();
  connectWS();
  refreshSessions();
})();
