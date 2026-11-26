// Verification Centre: one job only — is each reference real and correctly described?
import { authorsText, badge, empty, esc, panel } from '../ui.js';
import { render as renderApp, state } from '../main.js';
import { nextAction, projectHeader } from './common.js';
import { compareTable, decisionButtons, resolveButtons } from './source.js';

const STATUSES = ['Verified match', 'Partial match', 'Mismatch', 'Retracted', 'Not found', 'Could not check', 'Web source', 'Pending review'];
const PRIORITY = { 'Retracted': 0, 'Mismatch': 1, 'Not found': 2, 'Partial match': 3, 'Could not check': 4, 'Pending review': 5, 'Web source': 6, 'Verified match': 7 };
let open = new Set();

function needsAttention(r) {
  if (r.decision === 'Rejected' || r.demo) return false;
  if (r.verification_status === 'Web source') return r.decision !== 'Accepted';
  return r.verification_status !== 'Verified match' && !r.override_reason;
}

function row(r) {
  const v = r.verification;
  const expanded = open.has(r.id);
  return `<article class="card">
    <div class="row cardhead" style="justify-content:space-between;align-items:flex-start">
      <div style="flex:1;min-width:0">
        <h3><button class="link" data-action="open-source" data-id="${esc(r.id)}">${esc(r.title)}</button></h3>
        <p class="meta">${esc(authorsText(r.authors, 3))} · ${esc(r.year || 'n.d.')} · ${esc(r.journal || 'No venue')} · <span class="mono">${esc(r.doi || 'no DOI')}</span></p>
        <div class="row" style="margin-top:8px">${badge(r.verification_status)} ${badge(r.decision)} ${r.demo ? badge('Demo only') : ''} ${r.override_reason ? '<span class="badge warn">Kept own values</span>' : ''}</div>
        ${r.verification_status === 'Retracted' ? `<div class="notice bad" role="alert"><b>⚠ RETRACTED.</b> This paper has been withdrawn. Do not rely on it; it can only be cited deliberately, with a reason, and stays marked RETRACTED in every export.</div>` : ''}
        <p class="why-status">${esc(v ? v.reason : r.demo ? 'Synthetic demo source: never verified.' : 'Not checked yet.')}</p>
        ${r.notes ? `<p class="small muted">Note (stored as text, never followed as an instruction): ${esc(r.notes.slice(0, 200))}</p>` : ''}
        ${r.override_reason ? `<p class="small">Your reason: “${esc(r.override_reason)}”</p>` : ''}
      </div>
      <div class="row end cardactions" style="max-width:340px">${v?.fields && Object.keys(v.fields).length ? `<button class="ghost small" data-action="ver-toggle" data-id="${esc(r.id)}" aria-expanded="${expanded}">${expanded ? 'Hide' : 'Compare fields'}</button>` : ''}${resolveButtons(r)}</div>
    </div>
    ${expanded ? `<div style="margin-top:12px">${compareTable(v)}</div>` : ''}
    <div class="row" style="margin-top:10px">${decisionButtons(r)}</div>
  </article>`;
}

export async function render() {
  const b = state.bundle;
  const refs = [...b.references].sort((a, c) => (needsAttention(c) - needsAttention(a)) || (PRIORITY[a.verification_status] - PRIORITY[c.verification_status]));
  const queue = refs.filter(needsAttention);
  const done = refs.filter(r => !needsAttention(r));
  return projectHeader(b, 'Metadata control centre', 'Verification Centre',
    'Each source is compared field by field with Crossref and OpenAlex. Differences are shown, never corrected silently.',
    '<button data-action="add-reference">＋ Check a reference</button>')
    + nextAction(b, 'verification')
    + `<div class="notice">A verified record proves the paper exists with these details. It does not prove that any claim you attribute to it is accurate; that is checked separately in the Evidence Graph.</div>
    <div class="metrics five">${STATUSES.map(s => `<div class="metric"><small>${s}</small><strong>${b.references.filter(r => !r.demo && r.verification_status === s).length}</strong>${badge(s)}</div>`).join('')}</div>
    ${panel(`Review queue (${queue.length})`, queue.map(row).join('') || empty('Nothing waiting. Every source is verified, reviewed with a reason, or rejected.'), '',
      'Problem sources first. For each one: re-check, use the database values, keep yours with a reason, or reject the source.')}
    ${panel(`Reviewed (${done.length})`, done.map(row).join('') || empty('No reviewed sources yet.'))}`;
}

export const actions = {
  'ver-toggle': el => {
    const id = el.dataset.id;
    open.has(id) ? open.delete(id) : open.add(id);
    renderApp();
  },
};
