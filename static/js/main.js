// App shell: routing, shared state, the project picker and one delegated event handler.
// Views export render(ctx) -> HTML string and an `actions` map; buttons declare
// data-action="name" instead of inline onclick handlers.

import { api } from './api.js';
import { $, esc, toast, closeModal, closeDrawer, openModal, errorBox, loading } from './ui.js';
import * as overview from './views/overview.js';
import * as studio from './views/studio.js';
import * as verification from './views/verification.js';
import * as library from './views/library.js';
import * as evidenceView from './views/evidence.js';
import * as radar from './views/radar.js';
import * as citations from './views/citations.js';
import * as audit from './views/audit.js';
import * as settings from './views/settings.js';
import * as source from './views/source.js';

export const PAGES = [
  { key: 'overview', label: 'Overview', icon: '◫', view: overview },
  { key: 'studio', label: 'Research Studio', icon: '✧', view: studio, project: true },
  { key: 'verification', label: 'Verification Centre', icon: '✓', view: verification, project: true },
  { key: 'library', label: 'Research Library', icon: '▤', view: library },
  { key: 'evidence', label: 'Evidence Graph', icon: '⌘', view: evidenceView, project: true,
    lock: b => !b.project.plan_approved_at && 'Approve the research plan in Research Studio first.' },
  { key: 'radar', label: 'Contradiction Radar', icon: '◎', view: radar, project: true,
    lock: b => !b.claims.length && 'Write at least one claim in the Evidence Graph first.' },
  { key: 'citations', label: 'Citation Studio', icon: '❞', view: citations, project: true },
  { key: 'audit', label: 'Audit Trail', icon: '◷', view: audit },
  { key: 'settings', label: 'Settings', icon: '⚙', view: settings },
];

const store = (() => {
  try { return window.localStorage; } catch { return null; }
})();

export const state = {
  page: 'overview',
  status: null,
  projects: [],
  projectId: store?.getItem('veritas.project') || null,
  bundle: null,
};

const actions = {};
for (const p of PAGES) Object.assign(actions, p.view.actions || {});
Object.assign(actions, source.actions);

export function setProject(id) {
  state.projectId = id;
  try { store?.setItem('veritas.project', id || ''); } catch { /* private mode */ }
}

export async function loadProjects() {
  state.projects = await api.get('/projects');
  if (!state.projects.some(p => p.id === state.projectId)) setProject(state.projects[0]?.id || null);
  const picker = $('projectPicker');
  picker.innerHTML = state.projects.map(p => `<option value="${esc(p.id)}" ${p.id === state.projectId ? 'selected' : ''}>${esc(p.title)}</option>`).join('')
    || '<option value="">No projects yet</option>';
}

export async function loadBundle() {
  state.bundle = state.projectId ? await api.get(`/projects/${state.projectId}`) : null;
  return state.bundle;
}

export function go(page) {
  if (location.hash.slice(1) === page) render();
  else location.hash = page;
}

function renderNav() {
  const b = state.bundle;
  $('nav').innerHTML = `<div class="navlabel">WORKSPACE</div>` + PAGES.map(p => {
    const locked = p.lock && b && p.lock(b);
    return `<button data-action="nav" data-page="${p.key}" ${p.key === state.page ? 'aria-current="page"' : ''} ${locked ? `title="${esc(locked)}" aria-label="${esc(p.label)} (locked)"` : ''}>
      <span class="ico" aria-hidden="true">${p.icon}</span>${esc(p.label)}${locked ? '<span class="lock" aria-hidden="true">🔒</span><span class="sr-only"> (locked)</span>' : ''}</button>`;
  }).join('');
  const s = state.status;
  $('services').innerHTML = s ? `
    <div><span class="dot on"></span>OpenAlex + Crossref live</div>
    <div><span class="dot ${s.ai ? 'on' : 'off'}"></span>${s.ai ? `AI on (${esc(s.model)})` : 'AI off: rule-based mode'}</div>
    <div class="small" style="color:#8192ad;margin-top:6px">Evidence first. Always.</div>` : '';
}

function renderBanner() {
  const el = $('banner');
  const b = state.bundle;
  el.className = '';
  if (b?.project?.demo) {
    el.className = 'demo';
    el.innerHTML = `◇ <b>Demo data.</b> This sample project contains synthetic sources that can never be verified or cited. Searches you run here still return live results.`;
  } else if (state.status && !state.status.ai) {
    el.innerHTML = `Live mode · Search and verification use OpenAlex and Crossref in real time. AI features are off (no OPENAI_API_KEY), so planning, Red Team stance and summaries use transparent rule-based methods.`;
  } else {
    el.innerHTML = '';
  }
}

export async function render() {
  const page = PAGES.find(p => p.key === state.page) || PAGES[0];
  $('crumb').textContent = page.label;
  const app = $('app');
  try {
    if (!state.status) state.status = await api.get('/status');
    await loadProjects();
    await loadBundle();
  } catch (e) {
    app.innerHTML = errorBox(e.message, 'reload');
    return;
  }
  renderNav();
  renderBanner();
  if (page.project && !state.bundle) {
    app.innerHTML = `<div class="empty"><h2>No project yet</h2><p>Create a research project to start.</p><p style="margin-top:12px"><button data-action="new-project">＋ New research</button></p></div>`;
    return;
  }
  const locked = page.lock && page.lock(state.bundle);
  if (locked) {
    app.innerHTML = `<div class="empty"><h2>🔒 ${esc(page.label)} is not available yet</h2><p>${esc(locked)}</p></div>`;
    return;
  }
  if (!app.innerHTML) app.innerHTML = loading();
  try {
    app.innerHTML = await page.view.render(ctx);
    page.view.after?.(ctx);
  } catch (e) {
    console.error(e);
    app.innerHTML = errorBox(e.message, 'reload');
  }
}

export const ctx = { state, render, go, loadBundle, setProject, api };

// ---------------------------------------------------------------- global actions

Object.assign(actions, {
  'nav': el => { document.body.classList.remove('navopen'); go(el.dataset.page); },
  'toggle-nav': () => document.body.classList.toggle('navopen'),
  'close-modal': () => closeModal(),
  'close-drawer': () => closeDrawer(),
  'reload': () => { state.status = null; render(); },
  'new-project': () => openModal(`
    <h2 id="modalTitle">Start a research project</h2>
    <form data-submit="create-project" class="stack" style="margin-top:14px">
      <div class="field"><label for="np_title">Project title</label><input id="np_title" name="title" required maxlength="200"></div>
      <div class="field"><label for="np_q">Research question</label><textarea id="np_q" name="question" required minlength="5" placeholder="e.g. Does AI-powered personalisation improve customer experience in ecommerce, and what risks or limitations have researchers identified?"></textarea></div>
      <div class="formgrid">
        <div class="field"><label for="np_level">Academic level</label><select id="np_level" name="level"><option>Undergraduate</option><option>Postgraduate</option><option>Doctoral</option><option>Other</option></select></div>
        <div class="field"><label for="np_scope">Scope (optional)</label><input id="np_scope" name="scope" placeholder="e.g. retail, last 5 years"></div>
      </div>
      <button type="submit">Create project</button>
    </form>`),
  'create-project': async (form, data) => {
    const r = await api.post('/projects', data);
    setProject(r.id);
    closeModal();
    toast('Project created. Next: generate a plan.');
    go('studio');
  },
  'go': el => go(el.dataset.page),
});

async function run(name, el, data, ev) {
  const fn = actions[name];
  if (!fn) return console.warn('No action', name);
  try {
    await fn(el, data, ev);
  } catch (e) {
    console.error(e);
    toast(e.message || String(e), 'bad');
  }
}

document.addEventListener('click', ev => {
  const el = ev.target.closest('[data-action]');
  if (!el || el.disabled) return;
  ev.preventDefault();
  run(el.dataset.action, el, null, ev);
});
document.addEventListener('submit', ev => {
  const form = ev.target.closest('form[data-submit]');
  if (!form) return;
  ev.preventDefault();
  const data = {};
  new FormData(form).forEach((v, k) => { data[k] = v; });
  form.querySelectorAll('input[type=checkbox][name]').forEach(c => { data[c.name] = c.checked; });
  const btn = form.querySelector('[type=submit]');
  if (btn) btn.disabled = true;
  run(form.dataset.submit, form, data, ev).finally(() => { if (btn) btn.disabled = false; });
});
document.addEventListener('change', ev => {
  const el = ev.target.closest('[data-change]');
  if (el) run(el.dataset.change, el, el.value, ev);
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') closeDrawer();
  const el = ev.target.closest?.('[role="button"][data-action]');
  if (el && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); run(el.dataset.action, el, null, ev); }
});

$('projectPicker').addEventListener('change', e => {
  setProject(e.target.value);
  closeDrawer();
  render();
});

function route() {
  const key = decodeURIComponent(location.hash.slice(1));
  state.page = PAGES.some(p => p.key === key) ? key : 'overview';
  closeDrawer();
  $('app').innerHTML = '';
  render().then(() => $('app').focus({ preventScroll: true }));
}
window.addEventListener('hashchange', route);
route();
