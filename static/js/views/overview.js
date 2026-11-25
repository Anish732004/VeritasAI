import { api } from '../api.js';
import { badge, empty, esc, fmtDate, panel } from '../ui.js';
import { state, setProject, go } from '../main.js';
import { stepDots, STAGE_PAGE } from './common.js';

const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

export async function render() {
  const data = await api.get('/overview');
  const real = data.projects.filter(p => !p.demo);
  const sum = k => real.reduce((a, p) => a + p.counts[k], 0);
  const refs = sum('references'), claims = sum('claims');
  const reviewed = refs - sum('needs_review');
  const linked = sum('linked');
  const decided = sum('accepted');
  const vals = [pct(reviewed, refs), pct(linked, claims), pct(decided, claims)];
  const pulse = refs || claims ? Math.round(vals.reduce((a, b) => a + b, 0) / 3) : 0;
  const name = state.status?.name || 'Researcher';

  const metrics = [
    ['Projects', real.length], ['Saved sources', refs], ['Verified metadata', sum('verified')],
    ['Sources needing review', sum('needs_review')], ['Source-supported claims', sum('supported')], ['Claims without evidence', sum('unsupported')],
  ];

  const projects = data.projects.map(p => `
    <div class="projectcard">
      <div class="row" style="justify-content:space-between">
        <div style="min-width:0;flex:1"><h3>${esc(p.title)} ${p.demo ? badge('Demo only') : ''}</h3><p class="small">${esc(p.question)}</p></div>
        <button class="ghost small" data-action="open-project" data-id="${esc(p.id)}" data-page="${p.workflow.next ? STAGE_PAGE[p.workflow.next.key] : 'citations'}">
          ${p.workflow.next ? `Continue: ${esc(p.workflow.next.label)} →` : 'Open →'}</button>
      </div>
      ${stepDots(p.workflow)}
      <p class="small">${p.counts.references} sources · ${p.counts.verified} verified · ${p.counts.claims} claims · ${p.counts.supported} source-supported</p>
    </div>`).join('');

  return `
    <div class="heading"><div><div class="eyebrow">Research command centre</div><h1>Good to see you, ${esc(name)}.</h1>
      <p>Your research, with an evidence trail you can inspect.</p></div><button data-action="new-project">＋ New research</button></div>
    <div class="hero"><div><div class="eyebrow">The standard for responsible research</div><h2>Make every claim accountable.</h2>
      <p>Plan the search, verify every source against Crossref and OpenAlex, link claims to real passages, challenge them, and cite only what you approved.</p>
      <button data-action="go" data-page="studio">Open Research Studio →</button></div>
      <div aria-hidden="true"><svg width="180" height="150" viewBox="0 0 180 150"><g stroke="#819cff" fill="none"><path d="M15 75L65 25 115 75 165 25M15 75L65 125 115 75 165 125M65 25V125M165 25V125"/><circle cx="90" cy="75" r="62" opacity=".3"/></g>${[[15, 75], [65, 25], [65, 125], [115, 75], [165, 25], [165, 125]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="7" fill="#9eb5ff"/>`).join('')}</svg></div></div>
    <div class="metrics">${metrics.map(([l, v]) => `<div class="metric"><small>${l}</small><strong>${v}</strong><small>Real projects only</small></div>`).join('')}</div>
    <div class="grid">
      ${panel('Research integrity pulse', `
        <div class="pulse"><div class="ring" style="--arc:${pulse}%"><div><strong>${pulse}%</strong><small>WORKFLOW COVERAGE</small></div></div>
        <div class="bars">${[['Sources with reviewed verification', vals[0], `${reviewed}/${refs}`], ['Claims linked to a passage or labelled interpretation', vals[1], `${linked}/${claims}`], ['Claims accepted by you', vals[2], `${decided}/${claims}`]]
          .map(([l, v, f]) => `<small>${l} <b style="float:right">${f}</b></small><div class="bar" role="progressbar" aria-valuenow="${v}" aria-valuemin="0" aria-valuemax="100" aria-label="${l}"><i style="width:${v}%"></i></div>`).join('')}</div></div>
        <p>Progress indicators for the workflow, equally weighted. Not a measure of research quality or truth. Demo data is excluded.</p>`)}
      ${panel('Research projects', projects || empty('Create your first project.'))}
    </div>
    <div class="grid">
      ${panel('Claims awaiting your decision', data.attention.map(c => `<div class="lineitem"><div><h3>${esc(c.text)}</h3><p>${badge(c.status)} · ${esc(c.project_title)}</p></div>
        <button class="ghost small" data-action="open-project" data-id="${esc(c.project_id)}" data-page="evidence">Review</button></div>`).join('') || empty('No claims waiting.'))}
      ${panel('Recent activity', data.recent.map(a => `<div class="lineitem"><div><h3>${esc(a.action)}</h3><p>${esc(a.actor)} · ${esc((a.details || '').slice(0, 140))} · ${fmtDate(a.created_at)}</p></div></div>`).join('') || empty('Your decisions will appear here.'),
        '<button class="ghost small" data-action="go" data-page="audit">Full audit trail</button>')}
    </div>`;
}

export const actions = {
  'open-project': el => { setProject(el.dataset.id); go(el.dataset.page || 'studio'); },
};
