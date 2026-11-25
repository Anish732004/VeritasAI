// Shared rendering helpers. All dynamic text passes through esc() before reaching innerHTML.

export const $ = (id) => document.getElementById(id);

export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export const fmtDate = (d) => (d ? new Date(d).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '');

export function authorsText(authors, max = 4) {
  const names = (authors || []).map(a => [a.given, a.family].filter(Boolean).join(' ') || a.name || '').filter(Boolean);
  if (!names.length) return 'No authors listed';
  return names.length > max ? names.slice(0, max).join(', ') + ` +${names.length - max} more` : names.join(', ');
}

export function authorsInput(authors) {
  return (authors || []).map(a => [a.given, a.family].filter(Boolean).join(' ') || a.name || '').join('; ');
}

// Every status maps to a colour, an icon and its text label, so meaning never relies on colour alone.
const BADGES = {
  'Verified match': ['good', '✓'], 'Partial match': ['warn', '◐'], 'Mismatch': ['bad', '✕'],
  'Not found': ['bad', '?'], 'Pending review': ['warn', '…'],
  'Source-supported': ['good', '✓'], 'Reported, not independently checked': ['warn', '◐'],
  'AI interpretation': ['info', '✧'], 'Contradicted / qualified': ['bad', '⇄'], 'Demo only': ['demo', '◇'],
  'Accepted': ['good', '✓'], 'Rejected': ['bad', '✕'], 'Pending': ['', '○'],
  exact: ['good', '='], near: ['warn', '≈'], not_located: ['bad', '✕'], no_text: ['warn', '∅'],
  supports: ['good', '＋'], qualifies: ['warn', '◐'], challenges: ['bad', '−'], unclear: ['', '?'],
  high: ['bad', '!'], medium: ['warn', '!'], low: ['', 'i'],
};
const LABELS = {
  exact: 'Exact match', near: 'Near match', not_located: 'Not located in text', no_text: 'No source text to check',
  supports: 'Supports', qualifies: 'Qualifies', challenges: 'Challenges', unclear: 'Unclear',
};

export function badge(status, label = '', title = '') {
  const [cls, icon] = BADGES[status] || ['', '•'];
  return `<span class="badge ${cls}"${title ? ` title="${esc(title)}"` : ''}><span aria-hidden="true">${icon}</span>${esc(label || LABELS[status] || status)}</span>`;
}

export function tierBadge(venue) {
  if (!venue) return '';
  return `<span class="badge tier-${esc(venue.tier)}" title="${esc(venue.basis)}. A screening aid based on venue metrics, not a judgement of this paper.">Venue tier ${esc(venue.tier)}</span>`;
}

export function decisionBadge(d) { return badge(d || 'Pending'); }

export function heading(eyebrow, title, desc, action = '') {
  return `<div class="heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1>${desc ? `<p>${desc}</p>` : ''}</div>${action ? `<div class="row">${action}</div>` : ''}</div>`;
}

export function panel(title, body, extra = '', sub = '') {
  return `<section class="panel"><div class="panelhead"><h2>${esc(title)}</h2>${extra ? `<div class="row">${extra}</div>` : ''}${sub ? `<p>${sub}</p>` : ''}</div>${body}</section>`;
}

export const empty = (t) => `<div class="empty">${t}</div>`;
export const loading = (t = 'Loading…') => `<div class="loading" role="status">${esc(t)}</div>`;

export function errorBox(message, retryAction = '') {
  return `<div class="notice bad" role="alert">${esc(message)}${retryAction ? ` <button class="small ghost" data-action="${retryAction}">Retry</button>` : ''}</div>`;
}

let toastTimer;
export function toast(text, kind = '') {
  const t = $('toast');
  t.textContent = text;
  t.className = kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.textContent = ''; }, kind === 'bad' ? 7000 : 4000);
}

export function openModal(html) {
  $('modalContent').innerHTML = html + `<div class="row end" style="margin-top:16px"><button class="ghost" data-action="close-modal">Close</button></div>`;
  const m = $('modal');
  if (!m.open) m.showModal();
  m.querySelector('input, textarea, select')?.focus();
}
export function closeModal() { if ($('modal').open) $('modal').close(); }

export function openDrawer(html) {
  const d = $('drawer');
  d.innerHTML = `<button class="ghost small close" data-action="close-drawer" aria-label="Close source panel">✕ Close</button>` + html;
  d.classList.add('open');
  d.setAttribute('aria-hidden', 'false');
  d.focus?.();
}
export function closeDrawer() {
  const d = $('drawer');
  d.classList.remove('open');
  d.setAttribute('aria-hidden', 'true');
}

// Collects the values of every [name] control inside a form element.
export function formData(form) {
  const out = {};
  form.querySelectorAll('[name]').forEach(el => {
    out[el.name] = el.type === 'checkbox' ? el.checked : el.value;
  });
  return out;
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard.');
  } catch {
    openModal(`<h2 id="modalTitle">Copy manually</h2><textarea readonly style="min-height:160px">${esc(text)}</textarea>`);
  }
}

export function busy(button, text = 'Working…') {
  if (!button) return () => {};
  const old = button.innerHTML;
  button.disabled = true;
  button.innerHTML = esc(text);
  return () => { button.disabled = false; button.innerHTML = old; };
}

// In-app replacement for window.prompt / window.confirm. Resolves to the text (or true), or null if cancelled.
let pending = null;
export function ask({ title, message = '', input = false, placeholder = '', required = false, confirm = 'Confirm', danger = false }) {
  return new Promise(resolve => {
    pending = resolve;
    $('modalContent').innerHTML = `<h2 id="modalTitle">${esc(title)}</h2>${message ? `<p style="margin-top:6px">${esc(message)}</p>` : ''}
      <form data-ask class="stack" style="margin-top:14px">
        ${input ? `<label for="ask_input" class="sr-only">${esc(title)}</label><textarea id="ask_input" style="min-height:80px" placeholder="${esc(placeholder)}" ${required ? 'required' : ''}></textarea>` : ''}
        <div class="row end"><button type="button" class="ghost" data-ask-cancel>Cancel</button><button type="submit" class="${danger ? 'danger' : ''}">${esc(confirm)}</button></div>
      </form>`;
    const m = $('modal');
    if (!m.open) m.showModal();
    (m.querySelector('#ask_input') || m.querySelector('[type=submit]')).focus();
  });
}
function settle(value) {
  const r = pending;
  pending = null;
  closeModal();
  r?.(value);
}
document.addEventListener('submit', ev => {
  if (!ev.target.matches('form[data-ask]')) return;
  ev.preventDefault();
  const t = ev.target.querySelector('#ask_input');
  settle(t ? t.value.trim() : true);
}, true);
document.addEventListener('click', ev => {
  if (ev.target.closest('[data-ask-cancel]')) settle(null);
}, true);
document.getElementById('modal').addEventListener('close', () => { if (pending) settle(null); });
