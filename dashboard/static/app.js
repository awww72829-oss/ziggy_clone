/* Swiggy Fleet dashboard — vanilla, no build step. */

const S = {
  tab: localStorage.getItem('dash.tab') || 'overview',
  mobile: localStorage.getItem('dash.mobile') || '',
  sessions: [],
  proxies: [],
  logs: [],
  im: { addressId: '', addresses: [], query: '', results: [], cartRaw: null, payments: null,
        checkout: null, goTo: [], qr: false, coupons: [], coupon: '', fillers: [],
        bill: null, track: null },
  food: {
    addressId: '', addresses: [], restaurantId: '', restaurantName: '', lat: '', lng: '',
    menu: [], coupons: [], restaurants: [], dishes: [], cartRaw: null, payments: null,
    placed: null, coupon: '', qr: false, bill: null, track: null,
  },
  addr: {
    im: { open: false, lat: '', lng: '', draft: null, status: '' },
    food: { open: false, lat: '', lng: '', draft: null, status: '' },
  },
  templates: { items: {}, addresses: {} },
  shares: { list: [], last: null, kind: { im: 'cart', food: 'cart' } },
  group: { id: '', info: null, restaurantId: '', restaurantName: '', deeplink: '', qr: '',
           host: '', locked: false, members: 0, items: [], itemCount: 0 },
  login: { ticket: '', mobile: '' },
  history: { domain: 'im', rows: [], raw: null, loaded: false },
  wallet: { data: null, statement: null, loaded: false },
  offers: { food: null, payment: null, list: null, scratch: null },
  overview: { data: null },
  scan: { state: null, panels: null, probes: {} },
};

const TITLES = {
  scan: ['Scan', 'firebase panels → OTP capture → saved sessions'],
  overview: ['Overview', 'fleet health, liveness, and the active account'],
  sessions: ['Sessions', 'harvested accounts, liveness, proxy binding'],
  login: ['Login', 'phone + OTP, saved into the same sessions.json'],
  im: ['Instamart', 'search, cart, payment, checkout'],
  food: ['Food', 'menu, coupons, cart, place order'],
  history: ['History', 'past orders for the active session'],
  wallet: ['Wallet', 'Swiggy Money balance, statement, gift cards'],
  offers: ['Offers', 'restaurant coupons, payment offers, scratch cards'],
  proxies: ['Proxies', 'pool health and per-account egress'],
  logs: ['Logs', 'dashboard activity'],
};

/* ── plumbing ───────────────────────────────────────────────────────────── */
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

async function api(path, opts = {}) {
  const headers = { Accept: 'application/json' };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  const token = localStorage.getItem('dash.token') || '';
  if (token) headers['X-Dashboard-Token'] = token;
  const res = await fetch(path, {
    method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  let data;
  try { data = await res.json(); } catch { data = { ok: false, error: 'bad response' }; }
  if (res.status === 401) {
    const supplied = prompt('Dashboard token:');
    if (supplied) { localStorage.setItem('dash.token', supplied.trim()); return api(path, opts); }
    throw new Error('unauthorised');
  }
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(message, kind = '') {
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.textContent = message;
  $('#toasts').appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

function modal(title, payload) {
  $('#modal-title').textContent = title;
  $('#modal-body').textContent = typeof payload === 'string'
    ? payload : JSON.stringify(payload, null, 2);
  $('#modal').classList.remove('hidden');
}

function rawBlock(label, payload) {
  if (payload === null || payload === undefined) return '';
  return `<details class="raw"><summary>${esc(label)}</summary><pre>${esc(JSON.stringify(payload, null, 2))}</pre></details>`;
}

function dig(obj, keys) {
  if (!obj || typeof obj !== 'object') return null;
  for (const key of keys) {
    const value = obj[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  for (const value of Object.values(obj)) {
    if (value && typeof value === 'object') {
      const found = dig(value, keys);
      if (found !== null) return found;
    }
  }
  return null;
}

const money = (v) => (v === null || v === undefined || v === '' ? '—'
  : `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`);

const stamp = (v) => (v ? String(v).replace('T', ' ').replace('Z', '') : '—');

function pill(status) {
  const key = String(status || 'UNKNOWN').toUpperCase();
  const cls = key === 'LIVE' ? 'live' : key === 'EXPIRED' ? 'expired'
    : key === 'ERROR' ? 'error' : 'unknown';
  return `<span class="pill ${cls}">${esc(key)}</span>`;
}

const activeSession = () => S.sessions.find((s) => s.mobile === S.mobile) || null;

function needSession() {
  if (S.mobile) return true;
  $('#view').innerHTML = `<div class="empty">Pick a session in the left rail first —
    or <button class="btn primary" data-act="nav" data-tab="login">log a number in</button>.</div>`;
  return false;
}

/* ── cart helpers ───────────────────────────────────────────────────────── */
const cartKey = (domain) => `cart.${domain}.${S.mobile}`;

function cartGet(domain) {
  try { return JSON.parse(localStorage.getItem(cartKey(domain)) || '{}') || {}; }
  catch { return {}; }
}
function cartSave(domain, cart) { localStorage.setItem(cartKey(domain), JSON.stringify(cart)); }
function cartItems(domain) { return Object.values(cartGet(domain)); }
function cartTotal(domain) {
  return cartItems(domain).reduce((sum, i) => sum + (Number(i.price) || 0) * (Number(i.quantity) || 0), 0);
}
function cartBump(domain, id, delta, payload) {
  const cart = cartGet(domain);
  if (payload && !cart[id]) cart[id] = { ...payload, quantity: 0 };
  if (!cart[id]) return;
  cart[id].quantity = Math.max(0, (Number(cart[id].quantity) || 0) + delta);
  if (cart[id].quantity === 0) delete cart[id];
  cartSave(domain, cart);
  render();
}

/* ── data loaders ───────────────────────────────────────────────────────── */
async function loadSessions() {
  const data = await api('/api/sessions');
  S.sessions = data.sessions || [];
  if (!S.sessions.some((s) => s.mobile === S.mobile)) {
    const live = S.sessions.find((s) => s.sessionStatus === 'LIVE') || S.sessions[0];
    S.mobile = live ? live.mobile : '';
    localStorage.setItem('dash.mobile', S.mobile);
  }
  paintPicker();
}

function paintPicker() {
  const pick = $('#session-pick');
  pick.innerHTML = S.sessions.length
    ? S.sessions.map((s) => `<option value="${esc(s.mobile)}" ${s.mobile === S.mobile ? 'selected' : ''}>
        ${esc(s.mobile)} · ${esc(s.sessionStatus || 'UNKNOWN')}</option>`).join('')
    : '<option value="">no sessions</option>';
  const active = activeSession();
  $('#rail-status').innerHTML = active
    ? `${pill(active.sessionStatus)} <span class="mono">${esc(active.mobile)}</span>`
    : '<span class="muted small">no session selected</span>';
}

async function loadProxies(force = false) {
  const data = await api(`/api/proxies${force ? '?test=1' : ''}`);
  S.proxies = data.proxies || [];
}

async function loadScan(withPanels = true) {
  S.scan.state = await api('/api/scan');
  if (withPanels || !S.scan.panels) S.scan.panels = await api('/api/scan/panels');
}

async function loadTemplates() {
  const data = await api('/api/templates');
  S.templates = data.templates || { items: {}, addresses: {} };
}

let scanTicker = null;

function syncScanTicker() {
  const running = !!(S.scan.state && S.scan.state.running);
  if (running && !scanTicker) {
    scanTicker = setInterval(async () => {
      if (S.tab !== 'scan') return;
      try {
        await loadScan(false);
        render();
        if (!(S.scan.state || {}).running) syncScanTicker();
      } catch { /* keep the ticker honest, drop the frame */ }
    }, 2000);
  } else if (!running && scanTicker) {
    clearInterval(scanTicker);
    scanTicker = null;
  }
}

/* ── views ──────────────────────────────────────────────────────────────── */
function viewScan() {
  const st = S.scan.state || {};
  const panels = S.scan.panels || { active: [], disabled: [], duplicates: 0, total: 0 };
  const pct = st.panels_total
    ? Math.min(100, Math.round(((st.panels_done || 0) / st.panels_total) * 100)) : 0;
  const hitRate = st.attempts ? Math.round(((st.saved || 0) / st.attempts) * 100) : 0;
  const probes = S.scan.probes || {};

  const rows = panels.active.map((panel) => {
    const host = (panel.split('//')[1] || panel).split('/')[0];
    const probe = probes[panel];
    const verdict = !probe ? '<span class="muted small">not probed</span>'
      : probe.ok
        ? `<span class="pill live">${probe.devices} dev / ${probe.phones} nos</span> <span class="muted small">${probe.age_min ?? '—'}m old · ${probe.ms}ms</span>`
        : `<span class="pill error">${esc(probe.error || 'empty')}</span>`;
    return `<tr>
      <td class="mono small">${esc(host)}</td>
      <td>${verdict}</td>
      <td class="row"><button class="btn tiny" data-act="scan:probe" data-panel="${esc(panel)}">probe</button></td>
    </tr>`;
  }).join('');

  return `
    <div class="grid four">
      <div class="stat"><div class="k">state</div><div class="v small-val">${st.running
        ? '<span class="pill live">RUNNING</span>' : '<span class="pill unknown">IDLE</span>'}</div></div>
      <div class="stat"><div class="k">panels</div><div class="v">${st.panels_done || 0}<span class="muted small"> / ${st.panels_total || panels.active.length}</span></div></div>
      <div class="stat"><div class="k">devices</div><div class="v">${st.devices || 0}</div></div>
      <div class="stat"><div class="k">numbers</div><div class="v">${st.phones || 0}</div></div>
      <div class="stat"><div class="k">attempts</div><div class="v">${st.attempts || 0}</div></div>
      <div class="stat"><div class="k">saved</div><div class="v">${st.saved || 0}<span class="muted small"> ${hitRate}%</span></div></div>
      <div class="stat"><div class="k">otp timeouts</div><div class="v">${st.otp_timeouts || 0}</div></div>
      <div class="stat"><div class="k">skipped</div><div class="v">${st.skipped || 0}</div></div>
    </div>

    <div class="card">
      <div class="row between" style="margin-bottom:12px">
        <div class="row">
          ${st.running
            ? '<button class="btn danger" data-act="scan:stop">Stop scan</button>'
            : '<button class="btn primary" data-act="scan:start">Start scan</button>'}
          <button class="btn" data-act="scan:panels">Reload panels.txt</button>
        </div>
        <span class="muted small">${st.running
          ? `on ${esc(st.panel_current || '…')} · ${pct}%`
          : (st.finished_at ? `last finished ${esc(stamp(st.finished_at))}` : 'never run from here')}</span>
      </div>
      ${st.running ? `<div class="scanbar"><span style="width:${pct}%"></span></div>` : ''}

      <div class="row" style="margin-top:14px">
        <label class="small muted">workers <input id="scan-workers" type="number" min="1" max="64"
          value="${esc(st.workers || 10)}" style="width:70px"></label>
        <label class="small muted">max age (h) <input id="scan-age" type="number" min="1" max="720"
          value="${esc(Math.round((st.max_age_minutes || 2880) / 60))}" style="width:80px"></label>
        <label class="small muted">otp timeout (s) <input id="scan-timeout" type="number" min="10" max="300"
          value="${esc(st.otp_timeout || 90)}" style="width:90px"></label>
      </div>
      ${st.last_error ? `<p class="small" style="color:var(--danger)">${esc(st.last_error)}</p>` : ''}
    </div>

    <div class="split">
      <div class="card">
        <h2>Live log</h2>
        <pre class="scanlog">${esc((st.log || []).slice().reverse().join('\n')) || 'idle — nothing logged yet'}</pre>
      </div>

      <div class="card">
        <h2>Panels</h2>
        <p class="muted small">${panels.active.length} active · ${panels.disabled.length} parked in
        firebase_disabled.txt${panels.duplicates ? ` · ${panels.duplicates} duplicate hosts` : ''}</p>
        ${panels.active.length ? `<table>
          <thead><tr><th>host</th><th>probe</th><th></th></tr></thead>
          <tbody>${rows}</tbody></table>`
          : '<div class="empty">panels.txt has no firebase URLs. Drop some in and reload.</div>'}
      </div>
    </div>`;
}

function viewOverview() {
  const counts = S.sessions.reduce((acc, s) => {
    const key = String(s.sessionStatus || 'UNKNOWN').toUpperCase();
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const active = activeSession();
  const proxyBinding = S.proxies.length
    ? S.proxies.reduce((best, p) => (Math.min(p.accounts || 0, best.accounts ?? 99) === (p.accounts || 0) ? p : best), S.proxies[0])
    : null;

  return `
    <div class="grid four">
      <div class="stat"><div class="k">sessions</div><div class="v">${S.sessions.length}</div></div>
      <div class="stat"><div class="k">live</div><div class="v" style="color:var(--live)">${counts.LIVE || 0}</div></div>
      <div class="stat"><div class="k">expired</div><div class="v" style="color:var(--danger)">${counts.EXPIRED || 0}</div></div>
      <div class="stat"><div class="k">proxies</div><div class="v">${S.proxies.length}</div></div>
    </div>

    <div class="grid two">
      <div class="card">
        <h2>Active session</h2>
        ${active ? `
          <div class="row between" style="margin-bottom:12px">
            <div class="mono" style="font-size:16px">${esc(active.mobile)}</div>
            ${pill(active.sessionStatus)}
          </div>
          <table>
            <tr><th>customer</th><td class="mono">${esc(active.customerId || '—')}</td></tr>
            <tr><th>device</th><td>${esc(active.model || '—')} · Android ${esc(active.osVersion || '?')}</td></tr>
            <tr><th>app</th><td class="mono">${esc(active.appVersion || '—')} (${esc(active.versionCode || '—')})</td></tr>
            <tr><th>egress</th><td class="mono">${esc((active.proxy || 'direct').split('@').pop())}</td></tr>
            <tr><th>source</th><td>${esc(active.sourcePanelHost || '—')}</td></tr>
            <tr><th>checked</th><td class="mono">${esc(stamp(active.sessionStatusCheckedAt))}</td></tr>
            <tr><th>token</th><td class="mono">${esc(active.token_masked || '—')}</td></tr>
          </table>
          <div class="row" style="margin-top:12px">
            <button class="btn" data-act="session:check" data-mobile="${esc(active.mobile)}">Check liveness</button>
            <button class="btn" data-act="session:refresh" data-mobile="${esc(active.mobile)}">Re-mint token</button>
            <button class="btn" data-act="session:overview" data-mobile="${esc(active.mobile)}">Account snapshot</button>
            <button class="btn" data-act="session:geo" data-mobile="${esc(active.mobile)}">Set geo</button>
          </div>
        ` : '<div class="empty">No session yet. Farm one or log in a number.</div>'}
      </div>

      <div class="card">
        <h2>Fleet state</h2>
        <div class="row" style="margin-bottom:12px">
          ${Object.entries(counts).map(([k, v]) => `<span class="chip">${esc(k)} <code>${v}</code></span>`).join('') || '<span class="muted">nothing harvested yet</span>'}
        </div>
        ${rawBlock('proxies', S.proxies.map((p) => ({ label: p.label, ok: p.ok, ip: p.ip, accounts: p.accounts })))}
        <h2 style="margin-top:18px">Quick moves</h2>
        <div class="row">
          <button class="btn primary" data-act="session:check-all">Check every session</button>
          <button class="btn" data-act="nav" data-tab="im">Instamart order</button>
          <button class="btn" data-act="nav" data-tab="food">Food order</button>
          <button class="btn" data-act="nav" data-tab="login">Log a number in</button>
        </div>
        ${S.overview.data ? rawBlock('account snapshot', S.overview.data) : ''}
      </div>
    </div>`;
}

function viewSessions() {
  const rows = S.sessions.map((s) => `
    <tr>
      <td class="mono">${esc(s.mobile)}${s.mobile === S.mobile ? ' <span class="pill live">active</span>' : ''}
        ${s.mode === 'incognito' ? '<span class="pill">incognito</span>' : ''}</td>
      <td>${pill(s.sessionStatus)}</td>
      <td>${tagChips(s.tags)}</td>
      <td class="mono">${esc(s.customerId || '—')}</td>
      <td>${esc(s.model || '—')}</td>
      <td class="mono small">${esc((s.proxy || 'direct').split('@').pop())}</td>
      <td class="mono small">${esc(stamp(s.sessionStatusCheckedAt))}</td>
      <td class="row">
        <button class="btn tiny" data-act="session:select" data-mobile="${esc(s.mobile)}">use</button>
        <button class="btn tiny" data-act="session:check" data-mobile="${esc(s.mobile)}">check</button>
        <button class="btn tiny" data-act="session:refresh" data-mobile="${esc(s.mobile)}">re-mint</button>
        <button class="btn tiny" data-act="session:tags" data-mobile="${esc(s.mobile)}">tags</button>
        <button class="btn tiny" data-act="session:mode" data-mobile="${esc(s.mobile)}"
          data-mode="${s.mode === 'incognito' ? 'normal' : 'incognito'}">${s.mode === 'incognito' ? 'go visible' : 'incognito'}</button>
        <button class="btn tiny" data-act="session:overview" data-mobile="${esc(s.mobile)}">snapshot</button>
        <button class="btn tiny danger" data-act="session:delete" data-mobile="${esc(s.mobile)}">drop</button>
      </td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="row between" style="margin-bottom:12px">
        <div class="row">
          <button class="btn primary" data-act="session:check-all">Check all</button>
          <button class="btn" data-act="refresh">Reload</button>
        </div>
        <span class="muted small">${S.sessions.length} sessions · tags come from order history · incognito stops activity logging</span>
      </div>
      ${S.sessions.length ? `<table>
        <thead><tr><th>mobile</th><th>status</th><th>usage</th><th>customer</th><th>device</th><th>egress</th><th>checked</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>` : '<div class="empty">No sessions in sessions.json yet.</div>'}
    </div>`;
}

function viewLogin() {
  return `
    <div class="split">
      <div class="card">
        <h2>Phone + OTP</h2>
        <p class="muted small">Sends through the sticky proxy for that number, keeps the same cookie
        session for the verify, and writes a record identical to a farmed one.</p>
        <div class="row" style="margin:14px 0">
          <input id="login-mobile" class="wide" placeholder="10-digit mobile" inputmode="numeric"
            value="${esc(S.login.mobile)}">
          <button class="btn primary" data-act="login:send">Send OTP</button>
        </div>
        <div class="row">
          <input id="login-otp" class="wide" placeholder="OTP" inputmode="numeric">
          <button class="btn ${S.login.ticket ? 'primary' : ''}" data-act="login:verify"
            ${S.login.ticket ? '' : 'disabled'}>Verify</button>
        </div>
        ${S.login.ticket ? `<p class="muted small" style="margin-top:10px">ticket open ·
          OTP valid for 10 minutes</p>` : ''}
      </div>

      <div class="card">
        <h2>How it lands</h2>
        <div class="step done"><span class="n">1</span> fingerprint generated — model, app version, swuid</div>
        <div class="step"><span class="n">2</span> GET sms_otp on the account's proxy</div>
        <div class="step"><span class="n">3</span> POST login/verify on the same session</div>
        <div class="step"><span class="n">4</span> record written to sessions.json + minimal + individual</div>
        <div class="step"><span class="n">5</span> liveness checked, proxy bound to the number</div>
      </div>
    </div>`;
}

/* ── address + template helpers ─────────────────────────────────────────── */
const domState = (domain) => (domain === 'im' ? S.im : S.food);
const addrState = (domain) => S.addr[domain];

function addressForm(domain) {
  const st = addrState(domain);
  const draft = st.draft || {};
  const val = (key) => esc(draft[key] ?? '');
  const categories = ['HOME', 'WORK', 'OTHER'];
  const chosen = String(draft.addressCategory || 'HOME').toUpperCase();
  return `
    <div class="card" style="margin-top:10px;background:var(--panel-2)">
      <h2>New address <span class="muted small">${esc(domain)} · create_address</span></h2>
      <div class="formgrid">
        <label>name<input id="addr-userName" value="${val('userName')}" placeholder="receiver name"></label>
        <label>phone<input id="addr-userPhone" value="${val('userPhone')}" placeholder="10-digit mobile"></label>
        <label>flat / house<input id="addr-addressLine" value="${val('addressLine')}" placeholder="flat 4B, tower 2"></label>
        <label>street / area<input id="addr-addressLine2" value="${val('addressLine2')}" placeholder="12th main, indiranagar"></label>
        <label>locality<input id="addr-locality" value="${val('locality')}" placeholder="locality"></label>
        <label>city<input id="addr-city" value="${val('city')}" placeholder="bengaluru"></label>
        <label>pincode<input id="addr-postalCode" value="${val('postalCode')}" placeholder="560038"></label>
        <label>category
          <select id="addr-addressCategory">
            ${categories.map((c) => `<option value="${c}" ${c === chosen ? 'selected' : ''}>${c}</option>`).join('')}
          </select>
        </label>
        <label>tag<input id="addr-addressTag" value="${val('addressTag')}" placeholder="home / office"></label>
        <label>latitude<input id="addr-latitude" value="${esc(st.lat || draft.latitude || '')}" placeholder="12.9716"></label>
        <label>longitude<input id="addr-longitude" value="${esc(st.lng || draft.longitude || '')}" placeholder="77.5946"></label>
        <label class="span2">full address
          <textarea id="addr-fullAddress" rows="2"
            placeholder="flat 4B, tower 2, 12th main, indiranagar, bengaluru 560038">${val('fullAddress')}</textarea>
        </label>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="btn primary" data-act="addr:create" data-domain="${domain}">Create on Swiggy</button>
        <button class="btn" data-act="addr:build-full" data-domain="${domain}">Compose full address</button>
        <button class="btn" data-act="addr:form-hide" data-domain="${domain}">Hide</button>
      </div>
    </div>`;
}

function addressTools(domain) {
  const dom = domState(domain);
  const st = addrState(domain);
  const picks = dom.addresses || [];
  const tpls = Object.keys(S.templates.addresses || {});
  return `
    <div class="formgrid" style="margin:12px 0">
      <label class="span2">delivery address
        <select id="${domain}-address" data-act="${domain}:address">
          ${picks.length
            ? picks.map((a) => `<option value="${esc(a.id)}" ${a.id === dom.addressId ? 'selected' : ''}>${esc(a.label)} · ${esc(a.line)}</option>`).join('')
            : (dom.addressId ? `<option value="${esc(dom.addressId)}" selected>${esc(dom.addressId)}</option>`
                             : '<option value="">not loaded</option>')}
        </select>
      </label>
      <label>address template
        <select id="${domain}-addr-tpl" data-act="addr:tpl-apply" data-domain="${domain}">
          <option value="">—</option>
          ${tpls.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('')}
        </select>
      </label>
    </div>
    <div class="row" style="margin-bottom:12px">
      <button class="btn tiny" data-act="${domain}:addresses">load addresses</button>
      <button class="btn tiny" data-act="addr:locate" data-domain="${domain}">use current location</button>
      <button class="btn tiny" data-act="addr:form-show" data-domain="${domain}">new address</button>
      <button class="btn tiny" data-act="addr:tpl-save" data-domain="${domain}">save template</button>
      <button class="btn tiny danger" data-act="addr:delete" data-domain="${domain}">delete selected</button>
    </div>
    ${st.open ? addressForm(domain) : ''}
    ${st.status ? `<div class="muted small" style="margin-bottom:10px">${esc(st.status)}</div>` : ''}`;
}

function itemTemplateBar(domain) {
  const names = Object.keys(S.templates.items || {});
  return `
    <div class="row" style="margin-top:10px">
      <select id="${domain}-item-tpl" data-act="items:tpl-apply" data-domain="${domain}">
        <option value="">item template…</option>
        ${names.map((n) => `<option value="${esc(n)}">${esc(n)} · ${(S.templates.items[n] || []).length}</option>`).join('')}
      </select>
      <button class="btn tiny" data-act="items:tpl-save" data-domain="${domain}">save cart as template</button>
      <button class="btn tiny danger" data-act="items:tpl-del" data-domain="${domain}">delete template</button>
      <button class="btn tiny" data-act="items:share" data-domain="${domain}">copy cart payload</button>
      <button class="btn tiny" data-act="items:import" data-domain="${domain}">import payload</button>
    </div>`;
}

/* ── tags · bill · tracking · shares ────────────────────────────────────── */
function deepStrings(obj, out = []) {
  if (typeof obj === 'string') out.push(obj);
  else if (Array.isArray(obj)) obj.forEach((value) => deepStrings(value, out));
  else if (obj && typeof obj === 'object') Object.values(obj).forEach((value) => deepStrings(value, out));
  return out;
}

function qrBlock(payload) {
  const strings = deepStrings(payload).map((s) => s.trim());
  const image = strings.find((s) => s.startsWith('iVBOR') || s.startsWith('/9j/'));
  const intent = strings.find((s) => /^upi:\/\//i.test(s));
  if (!image && !intent) return '';
  return `
    <div class="row" style="margin:10px 0;align-items:flex-start;gap:14px;flex-wrap:wrap">
      ${image ? `<img alt="payment QR" style="width:170px;height:170px;background:#fff;border-radius:10px;padding:6px"
        src="data:image/png;base64,${esc(image)}">` : ''}
      <div class="small muted" style="min-width:180px">
        scan to pay<br>
        ${intent ? `<code style="word-break:break-all">${esc(intent)}</code><br>
          <button class="btn tiny" data-act="share:copy-text" data-text="${esc(intent)}">copy upi intent</button>` : ''}
      </div>
    </div>`;
}

function tagChips(tags) {
  const labels = (tags && tags.labels) || [];
  if (!labels.length) return '<span class="muted small">no orders yet</span>';
  return labels.map((label) => `<span class="chip tag">${esc(label)} used</span>`).join('');
}

function billCard(bill, title) {
  if (!bill) return '';
  const lines = bill.lines || [];
  const amount = (value) => (value === null || value === undefined ? '—' : money(value));
  return `
    <div class="card" style="margin-top:12px;background:var(--panel-2)">
      <div class="row between">
        <h2>${esc(title || 'Payable')}</h2>
        <span class="chip ${bill.verified ? 'live' : ''}">${bill.verified ? 'from cart' : 'unverified'}</span>
      </div>
      ${lines.length ? `<div class="bill">${lines.map((line) => `
        <div class="bill-line ${line.kind || ''}">
          <span>${esc(line.label)}</span>
          <span class="mono">${line.amount < 0 ? '−' + amount(Math.abs(line.amount)) : amount(line.amount)}</span>
        </div>`).join('')}</div>` : '<div class="empty">Cart has no bill block yet.</div>'}
      <div class="bill-line total">
        <span>to pay</span><span class="mono">${amount(bill.to_pay)}</span>
      </div>
      ${bill.savings !== null && bill.savings !== undefined
        ? `<div class="muted small">saved ${money(bill.savings)} on this cart</div>` : ''}
      ${bill.coupon && bill.coupon.code
        ? `<div class="muted small">coupon <code>${esc(bill.coupon.code)}</code>
             ${bill.coupon.discount ? '· ' + money(bill.coupon.discount) : ''}</div>` : ''}
      ${bill.error ? `<div class="muted small danger-text">${esc(bill.error)}</div>` : ''}
    </div>`;
}

function trackCard(track, title) {
  if (!track) return '';
  const timeline = track.timeline || [];
  return `
    <div class="card" style="margin-top:12px;background:var(--panel-2)">
      <div class="row between">
        <h2>${esc(title || 'Tracking')} <span class="mono muted small">${esc(track.order_id || '')}</span></h2>
        <span class="chip">${esc(track.status || 'unknown')}</span>
      </div>
      ${track.status_text ? `<div class="muted small" style="margin-bottom:8px">${esc(track.status_text)}</div>` : ''}
      ${track.eta ? `<div class="small">eta <code>${esc(track.eta)}</code></div>` : ''}
      ${timeline.length ? `<div class="timeline">${timeline.map((step) => `
        <div class="step-row ${step.done ? 'done' : ''}">
          <span class="dot"></span>
          <span class="grow">${esc(step.label)}</span>
          <span class="mono small muted">${esc(step.when)}</span>
        </div>`).join('')}</div>`
        : '<div class="empty">No timeline in the payload.</div>'}
      ${(track.links || []).length ? `<div class="row" style="margin-top:8px">
        ${track.links.map((link) => `<a class="btn tiny" href="${esc(link)}" target="_blank" rel="noreferrer">open link</a>`).join('')}
        <button class="btn tiny" data-act="share:copy-text" data-text="${esc((track.links || [])[0] || '')}">copy</button>
      </div>` : ''}
      ${track.error ? `<div class="muted small danger-text">${esc(track.error)}</div>` : ''}
    </div>`;
}

function shareCard(domain) {
  const dom = domState(domain);
  const pick = (dom.addresses || []).find((a) => a.id === dom.addressId) || {};
  const last = S.shares.last;
  const recent = (S.shares.list || []).filter((s) => s.state === 'live').slice(0, 4);
  return `
    <div class="card">
      <div class="row between">
        <h2>Share link <span class="muted small">one use · 24 h</span></h2>
        <button class="btn tiny" data-act="share:list">recent</button>
      </div>
      <p class="muted small">Carries the selected address, geo and this domain's cart.
        The receiver opens the link on any device, claims it once, and the payload
        lands here for import.</p>
      <div class="formgrid" style="margin:10px 0">
        <label>link type
          <select id="share-${domain}-kind" data-act="share:kind" data-domain="${domain}">
            ${[['cart', 'cart + address'], ['address', 'address only'],
               ['group', 'group cart'], ['order', 'order tracking']]
              .map(([value, label]) => `<option value="${value}" ${(S.shares.kind[domain] || 'cart') === value ? 'selected' : ''}>${label}</option>`)
              .join('')}
          </select>
        </label>
        <label>note<input id="share-${domain}-note" placeholder="optional note for the receiver"></label>
      </div>
      <div class="row">
        <button class="btn primary" data-act="share:create" data-domain="${domain}">create link</button>
        <button class="btn" data-act="share:claim" data-domain="${domain}">claim a link</button>
        ${pick.id ? `<span class="chip">address <code>${esc(String(pick.id).slice(0, 14))}</code></span>` : '<span class="muted small">no address selected</span>'}
      </div>
      ${last ? `
        <div class="row" style="margin-top:10px">
          <input class="wide mono" readonly value="${esc(last.url || last.path)}">
          <button class="btn tiny" data-act="share:copy-text" data-text="${esc(last.url || last.path)}">copy</button>
          ${last.url ? `<a class="btn tiny" href="${esc(last.url)}" target="_blank" rel="noreferrer">open</a>`
                     : `<a class="btn tiny" href="${esc(last.path)}" target="_blank" rel="noreferrer">open</a>`}
        </div>
        <div class="muted small">expires ${esc(last.expires || '—')} · ${esc(last.state || '')}</div>` : ''}
      ${recent.length ? `<div class="row" style="margin-top:10px;flex-wrap:wrap">
        ${recent.map((s) => `<span class="chip">${esc(s.token)} <code>${esc(s.state)}</code></span>`).join('')}
      </div>` : ''}
    </div>`;
}

function offerRows(payload) {
  const rows = (payload && payload.offers) || [];
  if (!rows.length) return '<div class="muted small">No payment offers came back.</div>';
  return `<div class="offers">${rows.map((row) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(row.title)}</div>
        <div class="meta">${esc(row.method)}${row.code ? ' · <code>' + esc(row.code) + '</code>' : ''}</div>
      </div>
      <div class="mono">${esc(row.savings || '—')}</div>
      <button class="btn tiny" data-act="offers:use-method" data-method="${esc(row.method)}">use</button>
    </div>`).join('')}</div>`;
}


function absorbGroup(payload) {
  const data = (payload && typeof payload === 'object' && payload.data) || {};
  const groupId = data.group_cart_id || dig(payload, ['group_cart_id', 'groupCartId']);
  if (groupId) S.group.id = String(groupId);
  if (data.shared_cart_deeplink) S.group.deeplink = String(data.shared_cart_deeplink);
  if (data.shared_cart_qr) S.group.qr = String(data.shared_cart_qr);
  if (data.host_user_id) S.group.host = String(data.host_user_id);
  if (data.locked_status !== undefined) S.group.locked = !!data.locked_status;
  const restaurant = data.restaurant_details || {};
  if (restaurant.restaurant_id) S.group.restaurantId = String(restaurant.restaurant_id);
  if (restaurant.restaurant_name) S.group.restaurantName = restaurant.restaurant_name;
  const carts = data.user_cart_map || {};
  S.group.members = Object.keys(carts).length;
  S.group.info = payload;
  return S.group;
}

function groupCard() {
  return `
    <div class="card">
      <h2>Group cart <span class="muted small">chkout /api/v1/shared_cart</span></h2>
      <p class="muted small">Create with the Food restaurant id above, then share the deeplink or QR.
        Guests join with the numeric group id.</p>
      <div class="row" style="margin:10px 0">
        <input id="group-restaurant" class="wide" placeholder="restaurant id"
          value="${esc(S.group.restaurantId || S.food.restaurantId || '')}">
        <button class="btn" data-act="group:create">create group</button>
      </div>
      <div class="row">
        <input id="group-id" class="wide" placeholder="group cart id" value="${esc(S.group.id || '')}">
        <button class="btn" data-act="group:join">join</button>
        <button class="btn" data-act="group:info">read</button>
        <button class="btn danger" data-act="group:leave">leave</button>
      </div>
      ${S.group.id ? `
        <div class="row" style="margin-top:10px">
          <span class="chip">id <code>${esc(S.group.id)}</code></span>
          <span class="chip">restaurant <code>${esc(S.group.restaurantId || '—')}</code></span>
          <span class="chip">members <code>${esc(S.group.members)}</code></span>
          <span class="chip">${S.group.locked ? 'locked' : 'open'}</span>
          ${S.group.host ? `<span class="chip">host <code>${esc(S.group.host)}</code></span>` : ''}
        </div>` : ''}
      ${S.group.deeplink ? `
        <div class="row" style="margin-top:10px">
          <input class="wide mono" readonly value="${esc(S.group.deeplink)}">
          <button class="btn tiny" data-act="group:copy">copy link</button>
          <a class="btn tiny" href="${esc(S.group.deeplink)}" target="_blank" rel="noreferrer">open</a>
        </div>` : ''}
      ${S.group.qr ? `
        <div style="margin-top:12px;display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
          <img alt="group cart QR" style="width:150px;height:150px;background:#fff;border-radius:10px;padding:6px"
            src="data:image/png;base64,${esc(S.group.qr)}">
          <div class="small muted">scan to join this group cart<br>
            ${S.group.restaurantName ? esc(S.group.restaurantName) + '<br>' : ''}
            guest joins with <code>${esc(S.group.id)}</code></div>
        </div>` : ''}
      ${rawBlock('group cart', S.group.info)}
      ${(S.group.items || []).length ? `
        <div style="margin-top:12px">
          <div class="row between"><div class="muted small">items in the shared cart</div>
            <button class="btn tiny" data-act="group:pull">pull into my cart</button></div>
          ${S.group.items.map((item) => `
            <div class="item">
              <div class="grow"><div class="name">${esc(item.name)}</div>
                <div class="meta">× ${esc(item.quantity)} · ${esc(item.member || 'member')}</div></div>
              <div class="mono">${money(item.price)}</div>
            </div>`).join('')}
        </div>` : ''}
    </div>`;
}

function viewIm() {
  if (!needSession()) return '';
  const cart = cartItems('im');
  const total = cartTotal('im');
  const results = S.im.results.map((item) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(item.name)}</div>
        <div class="meta">${esc(item.pack || '')} ${item.in_stock ? '' : '· out of stock'}</div>
      </div>
      <div class="mono">${money(item.price)}</div>
      <button class="btn tiny" data-act="im:add" data-spin="${esc(item.spinId)}">+</button>
    </div>`).join('');
  const goTo = S.im.goTo.map((item) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(item.name)}</div>
        <div class="meta">${esc(item.pack || '')}</div>
      </div>
      <div class="mono">${money(item.price)}</div>
      <button class="btn tiny" data-act="im:add-go" data-spin="${esc(item.spinId)}">+</button>
    </div>`).join('');
  const fillers = (S.im.fillers || []).map((item) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(item.name)}</div>
        <div class="meta">${esc(item.pack || '')}</div>
      </div>
      <div class="mono">${money(item.price)}</div>
      <button class="btn tiny" data-act="im:add-filler" data-spin="${esc(item.spinId)}">+</button>
    </div>`).join('');

  return `
    <div class="card">
      <div class="row between">
        <h2>Search <span class="muted small">MCP search_products</span></h2>
        <span class="muted small">Instamart · ${esc(S.mobile)}</span>
      </div>
      ${addressTools('im')}
      <div class="row" style="margin:0 0 12px">
        <input id="im-query" class="wide" placeholder="milk, eggs, atta…" value="${esc(S.im.query)}">
        <button class="btn primary" data-act="im:search">Search</button>
        <button class="btn" data-act="im:go-to">Your go-to items</button>
      </div>
      ${goTo.length ? `<div style="margin-bottom:10px">
        <div class="muted small" style="margin-bottom:6px">go-to items for ${esc(S.im.addressId || 'selected address')}</div>
        ${goTo}
      </div>` : ''}
      ${results ? `<div>${results}</div>` : '<div class="muted small">No results loaded.</div>'}
    </div>

    <div class="split">
      <div class="card">
        <h2>Your cart</h2>
        ${cart.length ? cart.map((i) => `
          <div class="item">
            <div class="grow">
              <div class="name">${esc(i.name)}</div>
              <div class="meta">${esc(i.pack || '')} · ${money(i.price)}</div>
            </div>
            <div class="qty">
              <button class="btn tiny" data-act="im:bump" data-spin="${esc(i.spinId)}" data-delta="-1">−</button>
              <span class="mono">${i.quantity}</span>
              <button class="btn tiny" data-act="im:bump" data-spin="${esc(i.spinId)}" data-delta="1">+</button>
            </div>
          </div>`).join('') : '<div class="empty">Empty. Search and add something.</div>'}
        <div class="row between" style="margin-top:14px">
          <strong>${money(total)}</strong>
          <span class="muted small">${cart.length} lines</span>
        </div>
        ${itemTemplateBar('im')}
        <div class="row" style="margin-top:12px">
          <button class="btn primary" data-act="im:push">Push to Swiggy</button>
          <button class="btn" data-act="im:load-cart">Read live cart</button>
          <button class="btn danger" data-act="im:clear-cart">Clear</button>
        </div>

        <div class="row" style="margin-top:14px">
          <input id="im-coupon" placeholder="coupon code" value="${esc(S.im.coupon)}">
          <button class="btn tiny" data-act="im:coupons">list coupons</button>
          <button class="btn tiny" data-act="im:use-coupon">apply</button>
          <button class="btn tiny danger" data-act="im:coupon-remove">remove</button>
        </div>
        ${(S.im.coupons || []).length ? `<div style="margin-top:10px">${S.im.coupons.map((c) => `
          <div class="item"><div class="grow"><div class="name mono">${esc(c.code)}</div>
            <div class="meta">${esc(c.title || '')}${c.savings ? ' · ' + esc(c.savings) : ''}</div></div>
            <button class="btn tiny" data-act="im:apply-code" data-code="${esc(c.code)}">use</button></div>`).join('')}</div>` : ''}

        <div class="row" style="margin-top:14px">
          <button class="btn tiny" data-act="im:fillers">find ₹1 fillers</button>
          <button class="btn tiny" data-act="im:bill">payable breakdown</button>
          <span class="muted small">fillers keep the cart above the minimum</span>
        </div>
        ${fillers ? `<div style="margin-top:10px">
          <div class="muted small" style="margin-bottom:6px">cheap line items</div>${fillers}</div>` : ''}
        ${billCard(S.im.bill, 'Instamart payable')}
        ${trackCard(S.im.track, 'Instamart tracking')}
        ${rawBlock('live cart', S.im.cartRaw)}
      </div>

      <div class="card">
        <h2>Checkout</h2>
        <div class="row" style="margin-bottom:10px">
          <button class="btn tiny" data-act="im:payments">Load payment options</button>
          <button class="btn tiny" data-act="im:payment-offers">Method offers</button>
          <span class="muted small">method must be one Swiggy lists</span>
        </div>
        <div class="row" style="margin-bottom:10px">
          <input id="im-method" class="wide" placeholder="Cash / UPI / SwiggyPay" value="${esc(localStorage.getItem('dash.im.method') || 'Cash')}">
        </div>
        <div class="row" style="margin-bottom:10px">
          <input id="im-intent" class="wide" placeholder="intentApp (UPI app id, optional)">
        </div>
        <label class="row small" style="margin-bottom:10px">
          <input type="checkbox" id="im-qr" ${S.im.qr ? 'checked' : ''}>
          pay by QR — sets <code>generateUPIQR</code> (only valid when the account lists a QR method)
        </label>
        <button class="btn primary" data-act="im:checkout" style="width:100%">Place order</button>
        ${S.offers.payment ? offerRows(S.offers.payment) : ''}
        ${rawBlock('payment options', S.im.payments)}
        ${S.im.checkout ? `
          <div class="card" style="margin-top:12px;background:var(--panel-2)">
            <h2>Checkout response</h2>
            <div class="row" style="margin:8px 0">
              <span class="chip">order <code>${esc(dig(S.im.checkout, ['orderId', 'order_id']) || '—')}</code></span>
              <span class="chip">paasId <code>${esc(dig(S.im.checkout, ['paasId']) || '—')}</code></span>
              <span class="chip">status <code>${esc(dig(S.im.checkout, ['statusCode', 'status']) ?? '—')}</code></span>
            </div>
            ${qrBlock(S.im.checkout)}
            <div class="row">
              <button class="btn" data-act="im:payment-status">Payment status</button>
              <button class="btn primary" data-act="im:confirm">Confirm order</button>
              <button class="btn" data-act="im:track">Track</button>
            </div>
            ${rawBlock('checkout payload', S.im.checkout)}
          </div>` : ''}
      </div>
    </div>

    ${groupCard()}
    ${shareCard('im')}`;
}

function viewFood() {
  if (!needSession()) return '';
  const cart = cartItems('food');
  const total = cartTotal('food');
  const menu = S.food.menu.map((item) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(item.name)}</div>
        <div class="meta mono">${esc(item.id)}</div>
      </div>
      <div class="mono">${money(item.price)}</div>
      <button class="btn tiny" data-act="food:add" data-id="${esc(item.id)}">+</button>
    </div>`).join('');
  const restaurants = S.food.restaurants.map((r) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(r.name)}${r.rating ? ` <span class="chip">★ ${esc(r.rating)}</span>` : ''}</div>
        <div class="meta">${esc(r.cuisines || '')}${r.area ? ' · ' + esc(r.area) : ''}${r.cost_for_two ? ' · ' + esc(r.cost_for_two) : ''}</div>
      </div>
      <button class="btn tiny" data-act="food:pick" data-id="${esc(r.id)}"
        data-lat="${esc(r.lat ?? '')}" data-lng="${esc(r.lng ?? '')}"
        data-name="${esc(r.name)}">open</button>
    </div>`).join('');
  const dishes = S.food.dishes.map((d) => `
    <div class="item">
      <div class="grow">
        <div class="name">${esc(d.name)}</div>
        <div class="meta">${esc(d.restaurant || '')}</div>
      </div>
      <div class="mono">${money(d.price)}</div>
      ${d.restaurant_id ? `<button class="btn tiny" data-act="food:pick" data-id="${esc(d.restaurant_id)}"
        data-name="${esc(d.restaurant || '')}">open</button>` : ''}
    </div>`).join('');

  return `
    <div class="card">
      <div class="row between">
        <h2>Find food</h2>
        <span class="muted small">Food · ${esc(S.mobile)}</span>
      </div>
      ${addressTools('food')}

      <div class="row" style="margin:0 0 12px">
        <input id="food-q" class="wide" placeholder="restaurant or dish name — biryani, pizza, dosa…"
          value="${esc(S.food.query || '')}">
        <button class="btn primary" data-act="food:find-restaurants">Find restaurants</button>
        <button class="btn" data-act="food:find-dishes">Find dishes</button>
      </div>

      ${restaurants ? `<div>${restaurants}</div>` : ''}
      ${dishes ? `<div style="margin-top:8px">${dishes}</div>` : ''}
      ${!restaurants && !dishes ? '<div class="muted small">Search first — no restaurant ID typing needed.</div>' : ''}
    </div>

    ${S.food.restaurantId ? `
    <div class="card">
      <div class="row between">
        <div>
          <h2>${esc(S.food.restaurantName || 'restaurant')} <span class="mono muted small">${esc(S.food.restaurantId)}</span></h2>
          <p class="muted small">menu at ${esc(S.food.lat || '—')}, ${esc(S.food.lng || '—')}</p>
        </div>
        <div class="row">
          <input id="food-page" placeholder="page" style="width:70px" value="1">
          <button class="btn" data-act="food:menu">Load menu</button>
        </div>
      </div>
      ${menu ? `<div>${menu}</div>` : '<div class="muted small">Menu not loaded.</div>'}
    </div>` : ''}

    <div class="split">
      <div class="card">
        <h2>Food cart</h2>
        ${cart.length ? cart.map((i) => `
          <div class="item">
            <div class="grow">
              <div class="name">${esc(i.name)}</div>
              <div class="meta">${money(i.price)}</div>
            </div>
            <div class="qty">
              <button class="btn tiny" data-act="food:bump" data-id="${esc(i.id)}" data-delta="-1">−</button>
              <span class="mono">${i.quantity}</span>
              <button class="btn tiny" data-act="food:bump" data-id="${esc(i.id)}" data-delta="1">+</button>
            </div>
          </div>`).join('') : '<div class="empty">Empty.</div>'}
        <div class="row between" style="margin-top:14px"><strong>${money(total)}</strong></div>
        ${itemTemplateBar('food')}
        <div class="row" style="margin-top:12px">
          <input id="food-coupon" placeholder="coupon code" value="${esc(S.food.coupon)}">
          <button class="btn" data-act="food:coupons">Fetch coupons</button>
          <button class="btn" data-act="food:apply-coupon">Apply</button>
        </div>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" data-act="food:push">Push cart</button>
          <button class="btn" data-act="food:load-cart">Read live cart</button>
        </div>
        ${S.food.coupons.length ? `<div style="margin-top:12px">${S.food.coupons.map((c) => `
          <div class="item"><div class="grow"><div class="name mono">${esc(c.code)}</div>
          <div class="meta">${esc(c.title || '')}${c.savings ? ' · ' + esc(c.savings) : ''}</div></div>
          <button class="btn tiny" data-act="food:use-coupon" data-code="${esc(c.code)}">use</button></div>`).join('')}</div>` : ''}
        <div class="row" style="margin-top:12px">
          <button class="btn tiny" data-act="food:bill">payable breakdown</button>
          <span class="muted small">coupon · free cash · extra cash · swiggy money</span>
        </div>
        ${billCard(S.food.bill, 'Food payable')}
        ${rawBlock('food cart', S.food.cartRaw)}
        ${rawBlock('coupons', S.food.coupons)}
      </div>

      <div class="card">
        <h2>Place order</h2>
        <div class="row" style="margin-bottom:10px">
          <button class="btn tiny" data-act="food:payments">Load payment options</button>
          <button class="btn tiny" data-act="food:payment-offers">Method offers</button>
        </div>
        <div class="row" style="margin-bottom:10px">
          <input id="food-method" class="wide" placeholder="paymentMethod" value="${esc(localStorage.getItem('dash.food.method') || '')}">
        </div>
        <label class="row small" style="margin-bottom:10px">
          <input type="checkbox" id="food-qr" ${S.food.qr ? 'checked' : ''}>
          pay by QR — sets <code>generateUPIQR</code> on the place call
        </label>
        <button class="btn primary" data-act="food:place" style="width:100%">Place food order</button>
        ${S.offers.payment ? offerRows(S.offers.payment) : ''}
        ${rawBlock('payment options', S.food.payments)}
        ${S.food.placed ? `
          <div class="card" style="margin-top:12px;background:var(--panel-2)">
            <h2>Place response</h2>
            <div class="row" style="margin:8px 0">
              <span class="chip">order <code>${esc(dig(S.food.placed, ['orderId', 'order_id']) || '—')}</code></span>
              <span class="chip">paasId <code>${esc(dig(S.food.placed, ['paasId']) || '—')}</code></span>
              <span class="chip">cart <code>${esc(dig(S.food.placed, ['cartId', 'cart_id']) || '—')}</code></span>
            </div>
            ${qrBlock(S.food.placed)}
            <div class="row">
              <button class="btn" data-act="food:payment-status">Payment status</button>
              <button class="btn primary" data-act="food:confirm">Confirm</button>
              <button class="btn" data-act="food:track">Track</button>
            </div>
            ${rawBlock('place payload', S.food.placed)}
          </div>` : ''}
        ${trackCard(S.food.track, 'Food tracking')}
      </div>
    </div>

    ${groupCard()}
    ${shareCard('food')}`;
}

function viewHistory() {
  if (!needSession()) return '';
  const rows = S.history.rows.map((order, idx) => `
    <tr>
      <td class="mono small">${esc(dig(order, ['orderId', 'order_id', 'id']) || '—')}</td>
      <td>${esc(dig(order, ['status', 'orderStatus', 'state']) || '—')}</td>
      <td class="num mono">${money(dig(order, ['total', 'orderTotal', 'grandTotal', 'amount']))}</td>
      <td class="small">${esc(dig(order, ['orderTime', 'createdAt', 'date']) || '—')}</td>
      <td class="row">
        <button class="btn tiny" data-act="history:raw" data-idx="${idx}">raw</button>
        <button class="btn tiny" data-act="history:link" data-idx="${idx}">track</button>
        ${dig(order, ['lat', 'latitude']) ? `<button class="btn tiny" data-act="history:track" data-idx="${idx}">live</button>` : ''}
      </td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="row between" style="margin-bottom:12px">
        <div class="row">
          <select id="history-domain" data-act="history:domain">
            <option value="im" ${S.history.domain === 'im' ? 'selected' : ''}>Instamart</option>
            <option value="food" ${S.history.domain === 'food' ? 'selected' : ''}>Food</option>
          </select>
          <button class="btn primary" data-act="history:load">Load orders</button>
        </div>
        <span class="muted small">${S.history.rows.length} rows</span>
      </div>
      ${S.history.rows.length ? `<table>
        <thead><tr><th>order</th><th>status</th><th class="num">amount</th><th>placed</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>` : '<div class="empty">Nothing loaded yet.</div>'}
      ${rawBlock('raw', S.history.raw)}
    </div>`;
}

function viewWallet() {
  if (!needSession()) return '';
  const data = S.wallet.data;
  return `
    <div class="grid two">
      <div class="card">
        <h2>Swiggy Money</h2>
        <div class="row between" style="margin:14px 0">
          <div>
            <div class="muted small">available to spend</div>
            <div style="font-size:30px;font-weight:700">${data ? esc(data.balance_fmt || money(data.balance)) : '—'}</div>
          </div>
          <button class="btn primary" data-act="wallet:load">Load balance</button>
        </div>
        <div class="row">
          <button class="btn" data-act="wallet:statement">Statement</button>
        </div>
        ${rawBlock('wallet raw', data)}
        ${rawBlock('statement', S.wallet.statement)}
      </div>

      <div class="card">
        <h2>Gift card</h2>
        <p class="muted small">PATCH /swiggymoney/voucher/claim — statusCode 0 and a positive
        value means it landed. Refresh the balance after.</p>
        <div class="row" style="margin:12px 0">
          <input id="gc-code" class="wide" placeholder="XXXX-XXXX-XXXX-XXXX">
          <input id="gc-secret" placeholder="PIN" style="width:100px" inputmode="numeric">
        </div>
        <button class="btn primary" data-act="wallet:claim">Claim</button>
      </div>
    </div>`;
}

function viewOffers() {
  if (!needSession()) return '';
  return `
    <div class="grid two">
      <div class="card">
        <h2>Restaurant coupons</h2>
        <div class="row" style="margin:12px 0">
          <input id="off-address" class="wide" placeholder="address id" value="${esc(S.food.addressId)}">
          <input id="off-restaurant" class="wide" placeholder="restaurant id" value="${esc(S.food.restaurantId)}">
          <button class="btn primary" data-act="offers:food">Fetch</button>
        </div>
        ${rawBlock('coupons', S.offers.food)}

        <h2 style="margin-top:18px">Payment offers</h2>
        <div class="row" style="margin:12px 0">
          <input id="off-lat" placeholder="lat" style="width:100px" value="${esc(S.food.lat)}">
          <input id="off-lng" placeholder="lng" style="width:100px" value="${esc(S.food.lng)}">
          <input id="off-value" placeholder="cart value" style="width:110px">
          <button class="btn" data-act="offers:payment">Fetch</button>
        </div>
        ${S.offers.payment ? offerRows(S.offers.payment) : ''}
        ${rawBlock('payment offers', S.offers.payment)}
      </div>

      <div class="card">
        <h2>Coupon list + scratch cards</h2>
        <div class="row" style="margin:12px 0">
          <button class="btn" data-act="offers:list">Load coupon list</button>
          <button class="btn" data-act="offers:scratch" data-action="assign">Assign scratch</button>
          <button class="btn" data-act="offers:scratch" data-action="unlock">Unlock scratch</button>
        </div>
        ${rawBlock('coupon list', S.offers.list)}
        ${rawBlock('scratch', S.offers.scratch)}
        <p class="muted small">Coupon-list and scratch hosts come from the APK dump, not a live
        capture — a non-200 here is the host guessing wrong, not the session dying.</p>
      </div>
    </div>`;
}

function viewProxies() {
  const rows = S.proxies.map((p) => `
    <tr>
      <td class="mono small">${esc(p.label)}</td>
      <td>${p.lls ? '<span class="pill">lls</span>' : ''}</td>
      <td class="num">${p.accounts || 0}</td>
      <td>${p.ok ? '<span class="pill live">up</span>' : `<span class="pill error">${esc(p.error || 'down')}</span>`}</td>
      <td class="mono small">${esc(p.ip || '—')}</td>
      <td class="num mono small">${p.latency_ms ? p.latency_ms + 'ms' : '—'}</td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="row between" style="margin-bottom:12px">
        <div class="row">
          <button class="btn primary" data-act="proxies:test">Test all</button>
          <button class="btn" data-act="proxies:reload">Reload proxies.txt</button>
        </div>
        <span class="muted small">${S.proxies.length} proxies · assignment is sticky per number</span>
      </div>
      ${S.proxies.length ? `<table>
        <thead><tr><th>endpoint</th><th></th><th class="num">accounts</th><th>health</th><th>exit ip</th><th class="num">latency</th></tr></thead>
        <tbody>${rows}</tbody></table>` : '<div class="empty">proxies.txt is empty — everything runs direct.</div>'}
    </div>

    <div class="card">
      <h2>Bind a session to a proxy</h2>
      <div class="row" style="margin-top:12px">
        <select id="bind-mobile">
          ${S.sessions.map((s) => `<option value="${esc(s.mobile)}">${esc(s.mobile)}</option>`).join('')}
        </select>
        <select id="bind-proxy">
          ${S.proxies.map((p) => `<option value="${esc(p.proxy)}">${esc(p.label)}</option>`).join('')}
        </select>
        <button class="btn" data-act="proxies:assign">Bind</button>
      </div>
    </div>`;
}

function viewLogs() {
  return `
    <div class="card">
      <div class="row between" style="margin-bottom:12px">
        <button class="btn" data-act="logs:load">Reload</button>
        <span class="muted small">${S.logs.length} entries</span>
      </div>
      ${S.logs.length ? `<table>
        <thead><tr><th>time</th><th>kind</th><th>mobile</th><th>detail</th></tr></thead>
        <tbody>${S.logs.map((e) => `<tr>
          <td class="mono small">${esc(stamp(e.ts))}</td>
          <td>${esc(e.kind)}</td>
          <td class="mono small">${esc(e.mobile)}</td>
          <td class="small">${esc(typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail))}</td>
        </tr>`).join('')}</tbody></table>` : '<div class="empty">Nothing logged yet.</div>'}
    </div>`;
}

/* ── render ─────────────────────────────────────────────────────────────── */
const VIEWS = {
  scan: viewScan,
  overview: viewOverview, sessions: viewSessions, login: viewLogin,
  im: viewIm, food: viewFood, history: viewHistory, wallet: viewWallet,
  offers: viewOffers, proxies: viewProxies, logs: viewLogs,
};

function render() {
  const [title, subtitle] = TITLES[S.tab] || TITLES.overview;
  $('#title').textContent = title;
  $('#subtitle').textContent = subtitle;
  document.querySelectorAll('.nav').forEach((node) => {
    node.classList.toggle('active', node.dataset.tab === S.tab);
  });
  paintPicker();
  $('#view').innerHTML = (VIEWS[S.tab] || viewOverview)();
}

async function refreshTab() {
  try {
    if (S.tab === 'overview' || S.tab === 'sessions') {
      await loadSessions();
      await loadProxies();
    } else if (S.tab === 'scan') {
      await loadScan();
      syncScanTicker();
    } else if (S.tab === 'proxies') {
      await loadSessions();
      await loadProxies();
    } else if (S.tab === 'logs') {
      S.logs = (await api('/api/logs')).entries || [];
    } else if (S.tab === 'history' && S.mobile) {
      const path = S.history.domain === 'food'
        ? `/api/food/${encodeURIComponent(S.mobile)}/orders?address_id=${encodeURIComponent(S.food.addressId)}`
        : `/api/im/${encodeURIComponent(S.mobile)}/orders`;
      const data = await api(path);
      S.history.rows = data.orders || [];
      S.history.raw = data.raw || null;
      S.history.loaded = true;
    }
    render();
  } catch (err) { toast(err.message, 'err'); }
}

/* ── actions ────────────────────────────────────────────────────────────── */
const needed = () => {
  if (!S.mobile) { toast('Pick a session first', 'err'); return false; }
  return true;
};

const ACTIONS = {
  'nav': ({ tab }) => { S.tab = tab; localStorage.setItem('dash.tab', tab); render(); refreshTab(); },
  'refresh': () => refreshTab(),
  'refresh-all': () => refreshTab(),
  'modal:close': () => $('#modal').classList.add('hidden'),

  'session:select': ({ mobile }) => {
    S.mobile = mobile;
    localStorage.setItem('dash.mobile', mobile);
    S.im = { ...S.im, results: [], goTo: [], cartRaw: null, checkout: null, addressId: '', addresses: [],
             coupons: [], fillers: [], bill: null, track: null };
    S.food = { ...S.food, menu: [], cartRaw: null, placed: null, coupons: [], addressId: '',
               addresses: [], restaurants: [], dishes: [], restaurantId: '', restaurantName: '',
               bill: null, track: null };
    S.addr = {
      im: { open: false, lat: '', lng: '', draft: null, status: '' },
      food: { open: false, lat: '', lng: '', draft: null, status: '' },
    };
    S.group = { id: '', info: null, restaurantId: '', restaurantName: '', deeplink: '', qr: '',
                host: '', locked: false, members: 0, items: [], itemCount: 0 };
    S.shares = { ...S.shares, last: null };
    S.history = { ...S.history, rows: [], raw: null };
    S.wallet = { data: null, statement: null, loaded: false };
    render();
  },

  'session:check': async ({ mobile }) => {
    toast(`checking ${mobile}…`);
    try {
      const data = await api('/api/sessions/check', { body: { mobiles: [mobile] } });
      const row = (data.results || [])[0] || {};
      toast(`${mobile}: ${row.status}${row.refreshed ? ' (token re-minted)' : ''}`,
        row.status === 'LIVE' ? 'ok' : 'err');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'session:check-all': async () => {
    toast('checking the whole fleet…');
    try {
      const data = await api('/api/sessions/check', { body: { mobiles: [] } });
      const results = data.results || [];
      const live = results.filter((r) => r.status === 'LIVE').length;
      toast(`${live}/${results.length} live`, 'ok');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'session:refresh': async ({ mobile }) => {
    try {
      const data = await api(`/api/sessions/${encodeURIComponent(mobile)}/refresh`, { body: {} });
      toast(data.ok && data.token ? `${mobile}: token re-minted` : `${mobile}: no token returned`,
        data.ok && data.token ? 'ok' : 'err');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'session:overview': async ({ mobile }) => {
    try {
      const data = await api(`/api/account/${encodeURIComponent(mobile)}`);
      S.overview.data = data;
      modal(`account ${mobile}`, data);
    } catch (err) { toast(err.message, 'err'); }
  },

  'session:geo': async ({ mobile }) => {
    const lat = prompt('latitude', '12.9716');
    if (lat === null) return;
    const lng = prompt('longitude', '77.5946');
    if (lng === null) return;
    try {
      await api(`/api/sessions/${encodeURIComponent(mobile)}/geo`, {
        body: { latitude: Number(lat), longitude: Number(lng) },
      });
      toast(`${mobile}: geo pinned to ${lat}, ${lng}`, 'ok');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'session:delete': async ({ mobile }) => {
    if (!confirm(`Drop ${mobile} from the stores?`)) return;
    try {
      await api(`/api/sessions/${encodeURIComponent(mobile)}`, { method: 'DELETE' });
      toast(`${mobile} removed`, 'ok');
      if (S.mobile === mobile) S.mobile = '';
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'login:send': async () => {
    const mobile = ($('#login-mobile') || {}).value || '';
    try {
      const data = await api('/api/login/send', { body: { mobile } });
      S.login.ticket = data.ticket;
      S.login.mobile = data.mobile;
      toast(`OTP sent to ${data.mobile}${data.proxy_used ? ' via proxy' : ' (direct)'}`, 'ok');
      render();
      $('#login-otp').focus();
    } catch (err) { toast(err.message, 'err'); }
  },

  'login:verify': async () => {
    const otp = ($('#login-otp') || {}).value || '';
    try {
      const data = await api('/api/login/verify', { body: { ticket: S.login.ticket, otp } });
      S.login.ticket = '';
      await loadSessions();
      S.mobile = data.session.mobile;
      localStorage.setItem('dash.mobile', S.mobile);
      toast(`session saved for ${data.session.mobile}`, 'ok');
      S.tab = 'overview';
      localStorage.setItem('dash.tab', S.tab);
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  /* instamart */
  'im:addresses': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/addresses`);
      S.im.addresses = data.addresses || [];
      if (!S.im.addresses.length) { toast('no addresses on this account', 'err'); return; }
      if (!S.im.addresses.some((a) => a.id === S.im.addressId)) S.im.addressId = S.im.addresses[0].id;
      S.addr.im.status = `${S.im.addresses.length} saved address(es)`;
      toast(`${S.im.addresses.length} addresses`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:search': async () => {
    if (!needed()) return;
    S.im.query = ($('#im-query') || {}).value || '';
    try {
      toast('searching…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/search?q=${encodeURIComponent(S.im.query)}&address_id=${encodeURIComponent(S.im.addressId)}`);
      S.im.results = data.items || [];
      if (!S.im.addressId && data.address_id) S.im.addressId = data.address_id;
      toast(`${S.im.results.length} variants`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:add': ({ spin }) => {
    const item = S.im.results.find((r) => r.spinId === spin);
    if (!item) return;
    cartBump('im', spin, 1, {
      spinId: item.spinId, skuId: item.skuId, name: item.name,
      pack: item.pack, price: item.price, quantity: 0,
    });
  },

  'im:bump': ({ spin, delta }) => cartBump('im', spin, Number(delta)),

  'im:go-to': async () => {
    if (!needed()) return;
    try {
      toast('loading go-to items…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/go-to?address_id=${encodeURIComponent(S.im.addressId)}`);
      S.im.goTo = data.items || [];
      if (!S.im.addressId && data.address_id) S.im.addressId = data.address_id;
      toast(`${S.im.goTo.length} go-to items`, S.im.goTo.length ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:add-go': ({ spin }) => {
    const item = S.im.goTo.find((r) => r.spinId === spin);
    if (!item) return;
    cartBump('im', spin, 1, {
      spinId: item.spinId, skuId: item.skuId, name: item.name,
      pack: item.pack, price: item.price, quantity: 0,
    });
  },

  'im:push': async () => {
    if (!needed()) return;
    const items = cartItems('im').map((i) => ({ spinId: i.spinId, skuId: i.skuId, quantity: i.quantity }));
    if (!items.length) { toast('cart is empty', 'err'); return; }
    try {
      toast('pushing cart…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/cart`, {
        body: { items, address_id: S.im.addressId },
      });
      S.im.cartRaw = data.raw;
      toast(data.ok ? 'cart pushed' : `cart update: ${data.error || 'failed'}`, data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:load-cart': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/cart`);
      S.im.cartRaw = data.raw;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:clear-cart': async () => {
    if (!needed()) return;
    try {
      await api(`/api/im/${encodeURIComponent(S.mobile)}/cart/clear`, { body: {} });
      cartSave('im', {});
      S.im.cartRaw = null;
      toast('cart cleared', 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:payments': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/payments`);
      S.im.payments = data.raw;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:checkout': async () => {
    if (!needed()) return;
    const method = (($('#im-method') || {}).value || 'Cash').trim();
    localStorage.setItem('dash.im.method', method);
    const intent = (($('#im-intent') || {}).value || '').trim();
    S.im.qr = !!(($('#im-qr') || {}).checked) || /qr/i.test(method);
    if (!confirm(`Place Instamart order on ${S.mobile} with ${method}${S.im.qr ? ' (QR)' : ''}?`)) return;
    try {
      toast('placing order…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/checkout`, {
        body: {
          address_id: S.im.addressId, payment_method: method,
          intent_app: intent, qr: S.im.qr,
        },
      });
      S.im.checkout = data.raw;
      toast(data.ok ? 'checkout accepted' : `checkout: ${data.error || 'rejected'}`,
        data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:payment-status': async () => {
    if (!S.im.checkout) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/payment-status`, {
        body: {
          paas_id: dig(S.im.checkout, ['paasId']) || '',
          order_id: dig(S.im.checkout, ['orderId', 'order_id']) || '',
          address_id: S.im.addressId,
        },
      });
      modal('payment status', data);
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:confirm': async () => {
    if (!S.im.checkout) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/confirm`, {
        body: {
          order_id: dig(S.im.checkout, ['orderId', 'order_id']) || '',
          paas_id: dig(S.im.checkout, ['paasId']) || '',
          address_id: S.im.addressId,
        },
      });
      toast(data.ok ? 'order confirmed' : `confirm: ${data.error || 'failed'}`, data.ok ? 'ok' : 'err');
      modal('confirm', data.raw || data);
    } catch (err) { toast(err.message, 'err'); }
  },

  /* food */
  'food:addresses': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/addresses`);
      S.food.addresses = data.addresses || [];
      if (!S.food.addresses.length) { toast('no addresses on this account', 'err'); return; }
      if (!S.food.addresses.some((a) => a.id === S.food.addressId)) S.food.addressId = S.food.addresses[0].id;
      const withGeo = S.food.addresses.find((a) => a.lat && a.lng) || S.food.addresses[0];
      if (withGeo.lat && withGeo.lng) {
        S.food.lat = String(withGeo.lat);
        S.food.lng = String(withGeo.lng);
        await api(`/api/sessions/${encodeURIComponent(S.mobile)}/geo`, {
          body: { latitude: Number(withGeo.lat), longitude: Number(withGeo.lng) },
        }).catch(() => {});
      }
      S.addr.food.status = `${S.food.addresses.length} saved address(es)`;
      toast(`${S.food.addresses.length} addresses`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:find-restaurants': async () => {
    if (!needed()) return;
    S.food.query = ($('#food-q') || {}).value || '';
    if (!S.food.query) { toast('type something to search', 'err'); return; }
    try {
      toast('searching restaurants…');
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/restaurants?q=${encodeURIComponent(S.food.query)}&address_id=${encodeURIComponent(S.food.addressId)}`);
      S.food.restaurants = data.restaurants || [];
      S.food.dishes = [];
      toast(`${S.food.restaurants.length} restaurants`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:find-dishes': async () => {
    if (!needed()) return;
    S.food.query = ($('#food-q') || {}).value || '';
    if (!S.food.query) { toast('type something to search', 'err'); return; }
    try {
      toast('searching dishes…');
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/search?q=${encodeURIComponent(S.food.query)}&address_id=${encodeURIComponent(S.food.addressId)}`);
      S.food.dishes = data.items || [];
      S.food.restaurants = [];
      toast(`${S.food.dishes.length} dishes`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:pick': ({ id, lat, lng, name }) => {
    S.food.restaurantId = id;
    S.food.restaurantName = name || '';
    if (lat) S.food.lat = String(lat);
    if (lng) S.food.lng = String(lng);
    S.food.restaurants = [];
    S.food.dishes = [];
    S.food.menu = [];
    render();
  },

  'food:menu': async () => {
    if (!needed()) return;
    if (!S.food.restaurantId) { toast('pick a restaurant first', 'err'); return; }
    if (!S.food.addressId) { toast('load an address first — the menu is address-scoped', 'err'); return; }
    try {
      toast('loading menu…');
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/menu?restaurant_id=${encodeURIComponent(S.food.restaurantId)}&address_id=${encodeURIComponent(S.food.addressId)}`);
      S.food.menu = data.items || [];
      toast(`${S.food.menu.length} dishes`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:add': ({ id }) => {
    const item = S.food.menu.find((m) => String(m.id) === String(id));
    if (!item) return;
    cartBump('food', id, 1, { id: item.id, name: item.name, price: item.price, quantity: 0 });
  },

  'food:bump': ({ id, delta }) => cartBump('food', id, Number(delta)),

  'food:push': async () => {
    if (!needed()) return;
    const items = cartItems('food').map((i) => ({ id: i.id, name: i.name, price: i.price, quantity: i.quantity }));
    if (!items.length) { toast('cart is empty', 'err'); return; }
    const coupon = ($('#food-coupon') || {}).value || '';
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/cart`, {
        body: {
          address_id: S.food.addressId, restaurant_id: S.food.restaurantId,
          items, coupon_code: coupon, flush_first: true,
        },
      });
      S.food.cartRaw = data.raw;
      toast(data.ok ? 'cart pushed' : `cart: ${data.error || 'failed'}`, data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:load-cart': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/cart?address_id=${encodeURIComponent(S.food.addressId)}`);
      S.food.cartRaw = data.raw;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:coupons': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/coupons?address_id=${encodeURIComponent(S.food.addressId)}&restaurant_id=${encodeURIComponent(S.food.restaurantId)}`);
      S.food.coupons = data.coupons || [];
      toast(`${S.food.coupons.length} coupons`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:use-coupon': ({ code }) => {
    S.food.coupon = code;
    const field = $('#food-coupon');
    if (field) field.value = code;
    toast(`coupon ${code} staged — push the cart`);
  },

  'food:apply-coupon': async () => {
    if (!needed()) return;
    const code = ($('#food-coupon') || {}).value || '';
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/coupon`, {
        body: { address_id: S.food.addressId, coupon_code: code },
      });
      toast(data.ok ? 'coupon applied' : `coupon: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      S.food.cartRaw = data.raw;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:payments': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/payments?address_id=${encodeURIComponent(S.food.addressId)}`);
      S.food.payments = data.raw;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:place': async () => {
    if (!needed()) return;
    const method = (($('#food-method') || {}).value || '').trim();
    localStorage.setItem('dash.food.method', method);
    S.food.qr = !!(($('#food-qr') || {}).checked) || /qr/i.test(method);
    if (!S.food.addressId || !S.food.restaurantId) { toast('address and restaurant required', 'err'); return; }
    if (!confirm(`Place food order on ${S.mobile}? ${method || 'default payment'}${S.food.qr ? ' (QR)' : ''}`)) return;
    try {
      toast('placing…');
      const body = {
        address_id: S.food.addressId, restaurant_id: S.food.restaurantId,
        generate_qr: S.food.qr,
      };
      if (method) body.paymentMethod = method;
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/place`, { body });
      S.food.placed = data.raw;
      toast(data.ok ? 'order placed' : `place: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:payment-status': async () => {
    if (!S.food.placed) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/payment-status`, {
        body: {
          paas_id: dig(S.food.placed, ['paasId']) || '',
          order_id: dig(S.food.placed, ['orderId', 'order_id']) || '',
          address_id: S.food.addressId,
          cart_id: dig(S.food.placed, ['cartId', 'cart_id']) || '',
        },
      });
      modal('payment status', data);
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:confirm': async () => {
    if (!S.food.placed) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/confirm`, {
        body: {
          order_id: dig(S.food.placed, ['orderId', 'order_id']) || '',
          paas_id: dig(S.food.placed, ['paasId']) || '',
          address_id: S.food.addressId,
          cart_id: dig(S.food.placed, ['cartId', 'cart_id']) || '',
        },
      });
      toast(data.ok ? 'confirmed' : `confirm: ${data.error || 'failed'}`, data.ok ? 'ok' : 'err');
      modal('confirm', data.raw || data);
    } catch (err) { toast(err.message, 'err'); }
  },

  /* history */
  'history:domain': () => { S.history.domain = ($('#history-domain') || {}).value || 'im'; },
  'history:load': async () => {
    if (!needed()) return;
    S.history.domain = ($('#history-domain') || {}).value || 'im';
    try {
      const path = S.history.domain === 'food'
        ? `/api/food/${encodeURIComponent(S.mobile)}/orders?address_id=${encodeURIComponent(S.food.addressId)}`
        : `/api/im/${encodeURIComponent(S.mobile)}/orders`;
      const data = await api(path);
      S.history.rows = data.orders || [];
      S.history.raw = data.raw || null;
      toast(`${S.history.rows.length} orders`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'history:raw': ({ idx }) => modal('order', S.history.rows[Number(idx)]),
  'history:link': async ({ idx }) => {
    const order = S.history.rows[Number(idx)] || {};
    const orderId = dig(order, ['orderId', 'order_id', 'id']) || '';
    if (!orderId) { toast('this row has no order id', 'err'); return; }
    try {
      toast(`reading tracking for ${orderId}…`);
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/track?order_id=${encodeURIComponent(orderId)}`);
      S.food.track = data;
      if (!data.ok) toast(data.error || 'no tracking payload', 'err');
      else toast(`status ${data.status}`, 'ok');
      if (S.tab !== 'food') { S.tab = 'food'; localStorage.setItem('dash.tab', 'food'); }
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'history:track': async ({ idx }) => {
    const order = S.history.rows[Number(idx)] || {};
    const orderId = dig(order, ['orderId', 'order_id', 'id']) || '';
    const lat = dig(order, ['lat', 'latitude']);
    const lng = dig(order, ['lng', 'longitude']);
    if (!orderId || lat === null || lng === null) { toast('no coordinates on this order', 'err'); return; }
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/track?order_id=${encodeURIComponent(orderId)}&lat=${lat}&lng=${lng}`);
      modal(`track ${orderId}`, data.raw || data);
    } catch (err) { toast(err.message, 'err'); }
  },

  /* wallet */
  'wallet:load': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/wallet/${encodeURIComponent(S.mobile)}`);
      S.wallet.data = data;
      toast(`balance ${data.balance_fmt || '—'}`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'wallet:statement': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/wallet/${encodeURIComponent(S.mobile)}/statement`);
      S.wallet.statement = data.raw;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'wallet:claim': async () => {
    if (!needed()) return;
    const code = (($('#gc-code') || {}).value || '').trim();
    const secret = (($('#gc-secret') || {}).value || '').trim();
    try {
      const data = await api(`/api/wallet/${encodeURIComponent(S.mobile)}/giftcard`, {
        body: { code, secret },
      });
      toast(data.ok ? 'gift card claimed' : `claim: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      S.wallet.data = null;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  /* offers */
  'offers:food': async () => {
    if (!needed()) return;
    const address = ($('#off-address') || {}).value || '';
    const restaurant = ($('#off-restaurant') || {}).value || '';
    try {
      const data = await api(`/api/offers/${encodeURIComponent(S.mobile)}/food?address_id=${encodeURIComponent(address)}&restaurant_id=${encodeURIComponent(restaurant)}`);
      S.offers.food = data;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'offers:payment': async () => {
    if (!needed()) return;
    const lat = ($('#off-lat') || {}).value || '';
    const lng = ($('#off-lng') || {}).value || '';
    const value = ($('#off-value') || {}).value || '0';
    try {
      const data = await api(`/api/offers/${encodeURIComponent(S.mobile)}/payment?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}&restaurant_id=${encodeURIComponent(S.food.restaurantId)}&cart_value=${encodeURIComponent(value)}`);
      S.offers.payment = data;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'offers:list': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/offers/${encodeURIComponent(S.mobile)}/list`);
      S.offers.list = data;
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'offers:scratch': async ({ action }) => {
    if (!needed()) return;
    try {
      const data = await api(`/api/offers/${encodeURIComponent(S.mobile)}/scratch`, {
        body: { action, payload: {} },
      });
      S.offers.scratch = data;
      toast(`scratch ${action}: ${data.ok ? 'ok' : (data.error || 'no response')}`,
        data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  /* addresses · templates · group cart */
  'addr:form-show': ({ domain }) => {
    const st = addrState(domain);
    st.open = true;
    if (!st.draft) st.draft = {};
    render();
  },

  'addr:form-hide': ({ domain }) => {
    addrState(domain).open = false;
    render();
  },

  'addr:build-full': ({ domain }) => {
    const parts = ['addr-addressLine', 'addr-addressLine2', 'addr-locality', 'addr-city', 'addr-postalCode']
      .map((id) => (($('#' + id) || {}).value || '').trim())
      .filter(Boolean);
    const field = $('#addr-fullAddress');
    if (field && parts.length) field.value = parts.join(', ');
  },

  'addr:locate': async ({ domain }) => {
    if (!needed()) return;
    const st = addrState(domain);
    if (!navigator.geolocation) { toast('browser has no geolocation', 'err'); return; }
    toast('asking the browser for a fix…');
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const lat = Number(pos.coords.latitude).toFixed(6);
      const lng = Number(pos.coords.longitude).toFixed(6);
      st.lat = lat;
      st.lng = lng;
      st.open = true;
      st.status = `pinned ${lat}, ${lng} · accuracy ${Math.round(pos.coords.accuracy || 0)} m`;
      if (domain === 'food') { S.food.lat = lat; S.food.lng = lng; }
      try {
        await api(`/api/sessions/${encodeURIComponent(S.mobile)}/geo`, {
          body: { latitude: Number(lat), longitude: Number(lng) },
        });
        toast(`session geo pinned to ${lat}, ${lng}`, 'ok');
      } catch (err) { toast(`address coords set; session geo failed: ${err.message}`, 'err'); }
      render();
    }, (err) => toast(`geolocation: ${err.message}`, 'err'),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  },

  'addr:create': async ({ domain }) => {
    if (!needed()) return;
    const read = (id) => (($('#' + id) || {}).value || '').trim();
    const fields = {
      userName: read('addr-userName'),
      userPhone: read('addr-userPhone'),
      addressLine: read('addr-addressLine'),
      addressLine2: read('addr-addressLine2'),
      locality: read('addr-locality'),
      city: read('addr-city'),
      postalCode: read('addr-postalCode'),
      addressCategory: read('addr-addressCategory') || 'HOME',
      addressTag: read('addr-addressTag'),
      fullAddress: read('addr-fullAddress'),
      domain,
    };
    const lat = read('addr-latitude');
    const lng = read('addr-longitude');
    if (lat && lng) { fields.latitude = Number(lat); fields.longitude = Number(lng); }
    if (!fields.fullAddress && fields.addressLine) {
      fields.fullAddress = [fields.addressLine, fields.addressLine2, fields.locality, fields.city, fields.postalCode]
        .filter(Boolean).join(', ');
    }
    try {
      toast('creating address…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/addresses/create`, { body: fields });
      const created = data.created || [];
      addrState(domain).status = created.length
        ? `created ${created[0].id}` : `HTTP ${data.status} — ${data.error || 'no address returned'}`;
      addrState(domain).draft = fields;
      if (created.length) {
        domState(domain).addresses = [...(domState(domain).addresses || []), ...created];
        domState(domain).addressId = created[0].id;
        addrState(domain).open = false;
        toast(`address ${created[0].id} created`, 'ok');
      } else {
        toast(`create: ${data.error || 'no address returned'}`, 'err');
      }
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'addr:delete': async ({ domain }) => {
    if (!needed()) return;
    const dom = domState(domain);
    if (!dom.addressId) { toast('no address selected', 'err'); return; }
    const pick = (dom.addresses || []).find((a) => a.id === dom.addressId) || {};
    const target = pick.raw_id || dom.addressId;
    if (!confirm(`Delete address ${dom.addressId} from ${S.mobile}?`)) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/addresses/${encodeURIComponent(target)}`,
        { method: 'DELETE' });
      dom.addresses = (dom.addresses || []).filter((a) => a.id !== dom.addressId);
      dom.addressId = dom.addresses.length ? dom.addresses[0].id : '';
      addrState(domain).status = `deleted — HTTP ${data.status}`;
      toast(data.ok ? 'address deleted' : `delete: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'addr:tpl-save': async ({ domain }) => {
    const dom = domState(domain);
    const name = prompt('template name', `${domain} address`);
    if (!name) return;
    const pick = (dom.addresses || []).find((a) => a.id === dom.addressId) || {};
    const payload = {
      addressId: dom.addressId || '',
      label: pick.label || '',
      line: pick.line || '',
      lat: pick.lat ?? (domain === 'food' ? S.food.lat : '') ?? '',
      lng: pick.lng ?? (domain === 'food' ? S.food.lng : '') ?? '',
      draft: addrState(domain).draft || null,
      domain,
    };
    try {
      await api('/api/templates/save', { body: { kind: 'addresses', name, payload } });
      await loadTemplates();
      toast(`address template ${name} saved`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'addr:tpl-apply': async ({ domain }) => {
    const name = (($(`#${domain}-addr-tpl`) || {}).value || '').trim();
    if (!name) return;
    const payload = (S.templates.addresses || {})[name];
    if (!payload) { toast('template missing', 'err'); return; }
    const dom = domState(domain);
    if (payload.addressId) dom.addressId = payload.addressId;
    if (domain === 'food' && payload.lat && payload.lng) {
      S.food.lat = String(payload.lat);
      S.food.lng = String(payload.lng);
    }
    addrState(domain).draft = payload.draft || null;
    addrState(domain).lat = payload.lat ? String(payload.lat) : '';
    addrState(domain).lng = payload.lng ? String(payload.lng) : '';
    addrState(domain).status = `template ${name} applied`;
    toast(`applied ${name}`, 'ok');
    render();
  },

  'items:tpl-save': async ({ domain }) => {
    const items = cartItems(domain);
    if (!items.length) { toast('cart is empty', 'err'); return; }
    const name = prompt('template name', `${domain} basket`);
    if (!name) return;
    try {
      await api('/api/templates/save', {
        body: { kind: 'items', name, payload: items.map((i) => ({ ...i })) },
      });
      await loadTemplates();
      toast(`${items.length} lines saved as ${name}`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'items:tpl-apply': ({ domain }) => {
    const name = (($(`#${domain}-item-tpl`) || {}).value || '').trim();
    if (!name) return;
    const lines = (S.templates.items || {})[name];
    if (!lines || !lines.length) { toast('template missing', 'err'); return; }
    const cart = {};
    lines.forEach((line) => {
      const key = domain === 'im' ? line.spinId : line.id;
      if (!key) return;
      cart[key] = { ...line, quantity: Number(line.quantity) || 1 };
    });
    cartSave(domain, cart);
    toast(`${lines.length} lines loaded from ${name}`, 'ok');
    render();
  },

  'items:tpl-del': async ({ domain }) => {
    const name = (($(`#${domain}-item-tpl`) || {}).value || '').trim();
    if (!name) { toast('pick a template first', 'err'); return; }
    if (!confirm(`Delete item template ${name}?`)) return;
    try {
      await api('/api/templates/delete', { body: { kind: 'items', name } });
      await loadTemplates();
      toast(`${name} deleted`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'group:create': async () => {
    if (!needed()) return;
    const restaurant = (($('#group-restaurant') || {}).value || S.food.restaurantId || '').trim();
    if (!restaurant) { toast('restaurant id required', 'err'); return; }
    try {
      const data = await api(`/api/group/${encodeURIComponent(S.mobile)}/create`, {
        body: { restaurant_id: restaurant },
      });
      S.group.restaurantId = restaurant;
      S.group.restaurantName = S.food.restaurantName || '';
      absorbGroup(data.raw || data);
      const created = data.ok && !!S.group.deeplink;
      toast(created ? `group ${S.group.id} created` : `create: ${data.error || 'no group returned'}`,
        created ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'group:join': async () => {
    if (!needed()) return;
    const id = (($('#group-id') || {}).value || S.group.id || '').trim();
    const restaurant = (($('#group-restaurant') || {}).value || S.group.restaurantId || '').trim();
    if (!id) { toast('group cart id required', 'err'); return; }
    if (!restaurant) { toast('restaurant id required — Swiggy rejects joins without it', 'err'); return; }
    try {
      const data = await api(`/api/group/${encodeURIComponent(S.mobile)}/join`, {
        body: { group_cart_id: id, restaurant_id: restaurant },
      });
      S.group.id = id;
      S.group.restaurantId = restaurant;
      S.group.info = data.raw || data;
      toast(data.ok ? `joined ${id}` : `join: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'group:info': async () => {
    if (!needed()) return;
    const id = (($('#group-id') || {}).value || S.group.id || '').trim();
    if (!id) { toast('group cart id required', 'err'); return; }
    try {
      const data = await api(`/api/group/${encodeURIComponent(S.mobile)}?group_cart_id=${encodeURIComponent(id)}`);
      S.group.id = id;
      absorbGroup(data.raw || data);
      S.group.items = data.items || [];
      S.group.itemCount = data.item_count || 0;
      toast(data.ok ? `group cart ${id} read · ${S.group.itemCount} items`
        : `read: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'group:leave': async () => {
    if (!needed()) return;
    const id = (($('#group-id') || {}).value || S.group.id || '').trim();
    if (!id) { toast('group cart id required', 'err'); return; }
    if (!confirm(`Leave and delete group cart ${id}?`)) return;
    try {
      const data = await api(`/api/group/${encodeURIComponent(S.mobile)}/leave`, {
        body: { group_cart_id: id },
      });
      toast(data.ok ? `left ${id}` : `leave: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      if (data.ok) {
        S.group = { ...S.group, id: '', deeplink: '', qr: '', info: null, members: 0, host: '',
                    items: [], itemCount: 0 };
      }
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'items:share': async ({ domain }) => {
    const items = cartItems(domain);
    if (!items.length) { toast('cart is empty', 'err'); return; }
    const payload = JSON.stringify({ domain, items: items.map((i) => ({ ...i })) }, null, 2);
    try {
      await navigator.clipboard.writeText(payload);
      toast('cart payload copied', 'ok');
    } catch {
      modal('cart share payload', payload);
    }
  },
  'items:import': ({ domain, silent, lines: supplied } = {}) => {
    let lines = supplied;
    if (!Array.isArray(lines) || !lines.length) {
      const raw = prompt(`paste a ${domain} cart payload (JSON)`);
      if (!raw) return;
      let parsed;
      try { parsed = JSON.parse(raw); } catch { toast('not valid JSON', 'err'); return; }
      lines = Array.isArray(parsed) ? parsed : (parsed.items || []);
    }
    if (!Array.isArray(lines) || !lines.length) { toast('payload has no items', 'err'); return; }
    const cart = cartGet(domain);
    let merged = 0;
    lines.forEach((line) => {
      const key = domain === 'im' ? (line.spinId || line.spin_id) : (line.id || line.spinId);
      if (!key) return;
      cart[key] = { ...line, quantity: Number(line.quantity) || 1 };
      merged += 1;
    });
    if (!merged) { toast('no usable lines in payload', 'err'); return; }
    cartSave(domain, cart);
    if (!silent) toast(`${merged} lines imported`, 'ok');
    render();
  },

  'group:copy': async () => {
    const text = S.group.deeplink
      || JSON.stringify({ group_cart_id: S.group.id, restaurant_id: S.group.restaurantId }, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      toast('group link copied', 'ok');
    } catch {
      modal('group cart share', text);
    }
  },

  /* share links · tags · modes · bill · tracking */
  'share:kind': ({ domain }) => {
    const value = (($(`#share-${domain}-kind`) || {}).value || 'cart');
    S.shares.kind = { ...S.shares.kind, [domain]: value };
  },

  'share:create': async ({ domain }) => {
    if (!needed()) return;
    const kind = (($(`#share-${domain}-kind`) || {}).value || 'cart').trim();
    const note = (($(`#share-${domain}-note`) || {}).value || '').trim();
    const dom = domState(domain);
    const pick = (dom.addresses || []).find((a) => a.id === dom.addressId) || {};
    const items = cartItems(domain).map((i) => ({
      id: i.spinId || i.id, spinId: i.spinId || '', name: i.name,
      quantity: i.quantity, price: i.price,
    }));
    const payload = {
      domain,
      items: kind === 'cart' ? items : [],
      address: pick.id ? { id: pick.id, label: pick.label, line: pick.line } : {},
      group: kind === 'group' && S.group.id
        ? { cart_id: S.group.id, deeplink: S.group.deeplink, restaurant_id: S.group.restaurantId }
        : null,
      order_id: kind === 'order'
        ? (dig(domain === 'im' ? S.im.checkout : S.food.placed,
               ['orderId', 'order_id']) || '') : '',
      note,
    };
    try {
      toast('minting link…');
      const data = await api('/api/share/create', {
        body: {
          mobile: S.mobile, kind, domain, note,
          address_id: pick.id || '',
          restaurant_id: dom.restaurantId || S.food.restaurantId || '',
          restaurant_name: dom.restaurantName || S.food.restaurantName || '',
          payload,
        },
      });
      S.shares.last = data;
      await ACTIONS['share:list']({ silent: true });
      toast(`link minted · ${data.expires || ''}`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'share:list': async ({ silent } = {}) => {
    try {
      const data = await api('/api/shares');
      S.shares.list = data.shares || [];
      if (!silent) { render(); toast(`${S.shares.list.length} links on file`); }
    } catch (err) { if (!silent) toast(err.message, 'err'); }
  },

  'share:copy-text': async ({ text }) => {
    if (!text) { toast('nothing to copy', 'err'); return; }
    try { await navigator.clipboard.writeText(text); toast('copied', 'ok'); }
    catch { modal('copy this', text); }
  },

  'share:claim': async ({ domain }) => {
    const raw = prompt('paste the share link, or just its token');
    if (!raw) return;
    const token = raw.trim().replace(/^.*\/s\//, '').replace(/[/?#].*$/, '');
    if (!token) { toast('no token in that', 'err'); return; }
    try {
      toast('claiming…');
      const data = await api(`/api/share/${encodeURIComponent(token)}/consume`, {
        body: { mobile: S.mobile },
      });
      const payload = data.payload || {};
      S.shares.last = { ...data, token, state: 'used', path: `/s/${token}`, url: '' };
      ACTIONS['share:absorb']({ domain: payload.domain || domain, payload });
      toast('claimed — payload landed in this tab', 'ok');
      await ACTIONS['share:list']({ silent: true });
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'share:absorb': ({ domain, payload }) => {
    const target = domState(domain) || S.im;
    if (payload.address && payload.address.id) {
      if (!(target.addresses || []).some((a) => a.id === payload.address.id)) {
        target.addresses = [...(target.addresses || []), {
          id: payload.address.id, raw_id: payload.address.id,
          label: payload.address.label || 'shared', line: payload.address.line || '',
        }];
      }
      target.addressId = payload.address.id;
    }
    if (payload.geo && payload.geo.lat !== undefined && domain === 'food') {
      S.food.lat = String(payload.geo.lat);
      S.food.lng = String(payload.geo.lng);
    }
    if (payload.group && payload.group.cart_id) {
      S.group.id = String(payload.group.cart_id);
      S.group.deeplink = String(payload.group.deeplink || '');
      S.group.restaurantId = String(payload.group.restaurant_id || '');
    }
    const lines = payload.items || [];
    if (lines.length) ACTIONS['items:import']({ domain, silent: true, lines });
    if (payload.restaurant_id && domain === 'food' && !S.food.restaurantId) {
      S.food.restaurantId = String(payload.restaurant_id);
      S.food.restaurantName = String(payload.restaurant_name || '');
    }
  },

  'session:tags': async ({ mobile }) => {
    try {
      toast('reading order history…');
      const data = await api(`/api/sessions/${encodeURIComponent(mobile)}/tags/refresh`, {
        body: { address_id: S.food.addressId || '' },
      });
      toast(data.ok ? `tags: ${(data.tags.labels || []).join(' · ')}` : `tags: ${data.error}`,
        data.ok ? 'ok' : 'err');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'session:mode': async ({ mobile, mode }) => {
    try {
      const data = await api(`/api/sessions/${encodeURIComponent(mobile)}/mode`, {
        body: { mode },
      });
      toast(`${mobile} → ${data.mode}`, 'ok');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:coupons': async () => {
    if (!needed()) return;
    try {
      toast('reading coupons…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/coupons?address_id=${encodeURIComponent(S.im.addressId)}`);
      S.im.coupons = data.coupons || [];
      if (!S.im.addressId && data.address_id) S.im.addressId = data.address_id;
      toast(data.coupons.length ? `${data.coupons.length} coupons` : (data.error || 'no coupons on this cart'),
        data.coupons.length ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:use-coupon': async ({ code } = {}) => {
    if (!needed()) return;
    const chosen = (code || (($('#im-coupon') || {}).value || '').trim());
    if (!chosen) { toast('coupon code required', 'err'); return; }
    if (!S.im.addressId) { toast('pick an address first — coupons are address-scoped', 'err'); return; }
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/coupon`, {
        body: { address_id: S.im.addressId, code: chosen },
      });
      S.im.coupon = chosen;
      toast(data.ok ? `coupon ${chosen} applied` : `coupon: ${data.error || 'rejected'}`,
        data.ok ? 'ok' : 'err');
      if (data.ok) await ACTIONS['im:bill']();
      else render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:apply-code': ({ code }) => ACTIONS['im:use-coupon']({ code }),

  'im:coupon-remove': async () => {
    if (!needed()) return;
    const code = (($('#im-coupon') || {}).value || S.im.coupon || '').trim();
    if (!S.im.addressId) { toast('pick an address first', 'err'); return; }
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/coupon/remove`, {
        body: { address_id: S.im.addressId, code },
      });
      toast(data.ok ? 'coupon removed' : `remove: ${data.error || 'rejected'}`, data.ok ? 'ok' : 'err');
      S.im.coupon = '';
      if (data.ok) await ACTIONS['im:bill']();
      else render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:fillers': async () => {
    if (!needed()) return;
    try {
      toast('hunting cheap line items…');
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/fillers?address_id=${encodeURIComponent(S.im.addressId)}`);
      S.im.fillers = data.items || [];
      if (!S.im.addressId && data.address_id) S.im.addressId = data.address_id;
      toast(S.im.fillers.length ? `${S.im.fillers.length} items ≤ ₹${data.max_price}`
        : (data.error || 'no fillers found'), S.im.fillers.length ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:add-filler': ({ spin }) => {
    const item = (S.im.fillers || []).find((r) => r.spinId === spin);
    if (!item) return;
    cartBump('im', spin, 1, {
      spinId: item.spinId, skuId: item.skuId, name: item.name,
      pack: item.pack, price: item.price, quantity: 0,
    });
  },

  'im:bill': async () => {
    if (!needed()) return;
    try {
      const data = await api(`/api/im/${encodeURIComponent(S.mobile)}/bill`);
      S.im.bill = data;
      toast(data.ok ? `to pay ${money(data.to_pay)}` : (data.error || 'no bill block'),
        data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:track': async () => {
    if (!needed() || !S.im.checkout) { toast('no checkout yet', 'err'); return; }
    const orderId = dig(S.im.checkout, ['orderId', 'order_id']) || '';
    if (!orderId) { toast('checkout has no order id', 'err'); return; }
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/track?order_id=${encodeURIComponent(orderId)}`);
      S.im.track = data;
      toast(data.ok ? `status ${data.status}` : (data.error || 'no tracking'), data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:bill': async () => {
    if (!needed()) return;
    if (!S.food.addressId) { toast('pick an address first', 'err'); return; }
    try {
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/bill?address_id=${encodeURIComponent(S.food.addressId)}`);
      S.food.bill = data;
      toast(data.ok ? `to pay ${money(data.to_pay)}` : (data.error || 'no bill block'),
        data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:track': async ({ orderId } = {}) => {
    if (!needed()) return;
    const target = orderId || dig(S.food.placed || {}, ['orderId', 'order_id']) || '';
    if (!target) { toast('no order id yet', 'err'); return; }
    try {
      toast('reading tracking…');
      const data = await api(`/api/food/${encodeURIComponent(S.mobile)}/track?order_id=${encodeURIComponent(target)}`);
      S.food.track = data;
      toast(data.ok ? `status ${data.status}` : (data.error || 'no tracking'), data.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'food:payment-offers': async () => {
    if (!needed()) return;
    const lat = S.food.lat || (($('#off-lat') || {}).value || '');
    const lng = S.food.lng || (($('#off-lng') || {}).value || '');
    if (!lat || !lng) { toast('set the session geo first', 'err'); return; }
    try {
      const value = Math.round(Number((S.food.bill && S.food.bill.item_total) || 0));
      const data = await api(`/api/offers/${encodeURIComponent(S.mobile)}/payment?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}&restaurant_id=${encodeURIComponent(S.food.restaurantId)}&cart_value=${value}`);
      S.offers.payment = data;
      toast(data.offers && data.offers.length ? `${data.offers.length} method offers`
        : (data.error || 'no payment offers'), data.offers && data.offers.length ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'im:payment-offers': async () => {
    if (!needed()) return;
    const lat = S.food.lat;
    const lng = S.food.lng;
    if (!lat || !lng) { toast('set the session geo first', 'err'); return; }
    try {
      const value = Math.round(Number((S.im.bill && S.im.bill.item_total) || 0));
      const data = await api(`/api/offers/${encodeURIComponent(S.mobile)}/payment?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}&cart_value=${value}`);
      S.offers.payment = data;
      toast(data.offers && data.offers.length ? `${data.offers.length} method offers` : 'no payment offers',
        data.offers && data.offers.length ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  'offers:use-method': ({ method }) => {
    if (!method) return;
    const guess = /cod|cash/i.test(method) ? 'Cash'
      : /upi|bhim|gpay|phonepe|paytm/i.test(method) ? 'UPI'
      : /card/i.test(method) ? 'CARD' : 'UPI';
    const imField = $('#im-method');
    if (imField) imField.value = guess;
    const foodField = $('#food-method');
    if (foodField) foodField.value = guess;
    const qr = /upi/i.test(guess);
    const imQr = $('#im-qr');
    if (imQr) imQr.checked = qr;
    const foodQr = $('#food-qr');
    if (foodQr) foodQr.checked = qr;
    S.im.qr = qr;
    S.food.qr = qr;
    localStorage.setItem('dash.im.method', guess);
    localStorage.setItem('dash.food.method', guess);
    toast(`method set to ${guess}${qr ? ' · QR on' : ''} (${method})`, 'ok');
  },

  'group:pull': ({ domain } = {}) => {
    const lines = S.group.items || [];
    if (!lines.length) { toast('group cart has no items', 'err'); return; }
    const target = domain || 'food';
    const cart = cartGet(target);
    let merged = 0;
    lines.forEach((line) => {
      const key = String(line.id || '');
      if (!key) return;
      cart[key] = {
        id: key, name: line.name, price: line.price,
        quantity: Number(line.quantity) || 1,
      };
      merged += 1;
    });
    if (!merged) { toast('nothing translatable in that cart', 'err'); return; }
    cartSave(target, cart);
    toast(`${merged} lines pulled into the ${target} cart`, 'ok');
    render();
  },

  /* scan */
  'scan:start': async () => {
    const workers = Number(($('#scan-workers') || {}).value || 10);
    const hours = Number(($('#scan-age') || {}).value || 48);
    const timeout = Number(($('#scan-timeout') || {}).value || 90);
    try {
      await api('/api/scan/start', {
        body: { workers, max_age_minutes: Math.round(hours * 60), otp_timeout: timeout },
      });
      toast('scan started', 'ok');
      S.scan.probes = {};
      await loadScan();
      syncScanTicker();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'scan:stop': async () => {
    try {
      await api('/api/scan/stop', { body: {} });
      toast('stop requested — in-flight requests finish first');
      await loadScan(false);
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'scan:panels': async () => {
    try {
      S.scan.panels = await api('/api/scan/panels/reload', { body: {} });
      toast(`${S.scan.panels.active.length} active panels`, 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'scan:probe': async ({ panel }) => {
    try {
      toast('probing panel…');
      const result = await api('/api/scan/panels/probe', { body: { panel } });
      S.scan.probes[panel] = result;
      toast(result.ok ? `${result.devices} devices / ${result.phones} numbers`
        : (result.error || 'no devices'), result.ok ? 'ok' : 'err');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  /* proxies */
  'proxies:test': async () => {
    try {
      toast('probing the pool…');
      await loadProxies(true);
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'proxies:reload': async () => {
    try {
      await api('/api/proxies/reload', { body: {} });
      await loadProxies();
      toast('pool reloaded', 'ok');
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
  'proxies:assign': async () => {
    const mobile = ($('#bind-mobile') || {}).value || '';
    const proxy = ($('#bind-proxy') || {}).value || '';
    try {
      await api('/api/proxies/assign', { body: { mobile, proxy } });
      toast(`${mobile} bound to ${proxy.split('@').pop()}`, 'ok');
      await loadSessions();
      render();
    } catch (err) { toast(err.message, 'err'); }
  },

  /* logs */
  'logs:load': async () => {
    try {
      S.logs = (await api('/api/logs')).entries || [];
      render();
    } catch (err) { toast(err.message, 'err'); }
  },
};

/* ── wiring ─────────────────────────────────────────────────────────────── */
document.addEventListener('click', async (event) => {
  const node = event.target.closest('[data-act]');
  if (!node || node.tagName === 'SELECT' || node.tagName === 'INPUT') return;
  const handler = ACTIONS[node.dataset.act];
  if (!handler) return;
  event.preventDefault();
  node.disabled = true;
  try {
    await handler(node.dataset);
  } catch (err) {
    toast(err.message || String(err), 'err');
  } finally {
    node.disabled = false;
  }
});

document.addEventListener('change', async (event) => {
  const node = event.target.closest('select[data-act]');
  if (!node) return;
  if (node.id === 'session-pick') {
    ACTIONS['session:select']({ mobile: node.value });
    return;
  }
  if (node.dataset.act === 'history:domain') {
    S.history.domain = node.value;
    return;
  }
  if (node.dataset.act === 'im:address') { S.im.addressId = node.value; return; }
  if (node.dataset.act === 'food:address') { S.food.addressId = node.value; return; }
  const handler = ACTIONS[node.dataset.act];
  if (!handler) return;
  try { await handler(node.dataset); } catch (err) { toast(err.message, 'err'); }
});

$('#session-pick').addEventListener('change', (event) => {
  ACTIONS['session:select']({ mobile: event.target.value });
});

/* boot */
(async () => {
  try {
    await Promise.all([loadSessions(), loadProxies(), loadTemplates(),
      api('/api/logs').then((d) => { S.logs = d.entries || []; })]);
  } catch (err) {
    toast(err.message, 'err');
  }
  render();
  if (S.tab === 'overview' || S.tab === 'sessions') refreshTab();
})();
