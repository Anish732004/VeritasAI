// Citation Studio: approval checkpoint, CSL-formatted bibliography, Citation Risk Review, export.
import { api, qs } from '../api.js';
import { badge, copyText, empty, esc, panel, toast } from '../ui.js';
import { render as renderApp, state } from '../main.js';
import { nextAction, projectHeader } from './common.js';
import { decisionButtons } from './source.js';

let style = 'APA 7';
let current = null;

export async function render() {
  const b = state.bundle;
  const [bib, disc] = await Promise.all([api.get(`/projects/${state.projectId}/bibliography` + qs({ style })), api.get(`/projects/${state.projectId}/disclosure`)]);
  current = bib;
  const pendingRefs = b.references.filter(r => !r.demo && r.decision === 'Pending');
  const pendingClaims = b.claims.filter(c => !c.demo && c.decision === 'Pending');
  const blocked = bib.blockers.length > 0;
  const exportLink = fmt => `/api/projects/${encodeURIComponent(state.projectId)}/export` + qs({ style, fmt });

  return projectHeader(b, 'Responsible scholarly writing', 'Citation Studio', 'References are formatted by a standard CSL engine from reviewed, structured metadata. Nothing here is written by a language model.')
    + nextAction(b, 'citations')
    + panel('Approval checkpoint', `
      ${blocked ? `<div class="notice warn"><b>Export is locked.</b><ul>${bib.blockers.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '<div class="notice good">✓ Every source and claim has your decision. Export is unlocked.</div>'}
      ${pendingRefs.length ? `<h4 style="margin:12px 0 6px">Sources awaiting your decision</h4>${pendingRefs.map(r => `<div class="lineitem"><div><h3><button class="link" data-action="open-source" data-id="${esc(r.id)}">${esc(r.title)}</button></h3><p>${badge(r.verification_status)}</p></div><div class="row">${decisionButtons(r)}</div></div>`).join('')}` : ''}
      ${pendingClaims.length ? `<h4 style="margin:12px 0 6px">Claims awaiting your decision</h4>${pendingClaims.map(c => `<div class="lineitem"><div><h3>${esc(c.text)}</h3><p>${badge(c.status)} ${esc(c.status_reason || '')}</p></div><div class="row">
        <button class="ok small" data-action="claim-decide" data-id="${esc(c.id)}" data-d="Accepted">✓ Accept</button><button class="danger small" data-action="claim-decide" data-id="${esc(c.id)}" data-d="Rejected">✕ Reject</button></div></div>`).join('')}` : ''}`,
      '', 'Blueprint checkpoint: before export, the student approves claims and references.')
    + panel('Bibliography', `
      <div class="row" style="margin-bottom:12px"><label for="cite_style">Style</label><select id="cite_style" data-change="cite-style">${bib.styles.map(s => `<option ${s === style ? 'selected' : ''}>${s}</option>`).join('')}</select>
        ${['txt', 'html', 'bib', 'csl'].map(f => blocked ? `<button class="ghost small" disabled title="Locked until the checkpoint passes">Export .${f === 'csl' ? 'json (CSL)' : f}</button>`
          : `<a class="small" href="${exportLink(f)}" download data-export>Export .${f === 'csl' ? 'json (CSL)' : f}</a>`).join(' · ')}
        <button class="ghost small" data-action="cite-copy-all" ${bib.entries.length ? '' : 'disabled'}>Copy all</button></div>
      ${style !== 'APA 7' ? '<p class="small muted">APA 7 is the reference style the project is tested against. MLA, Harvard and Chicago come from the same CSL engine; check given-name formatting by hand.</p>' : ''}
      ${bib.entries.map((e, i) => `<div class="bibentry"><p class="entry">${e.html}</p>
        <div class="row" style="margin-top:6px"><span class="small muted">In-text: ${esc(e.in_text)}</span><button class="ghost small" data-action="cite-copy" data-i="${i}">Copy</button></div>
        ${e.mark ? `<div class="notice ${e.status === 'Retracted' ? 'bad' : 'warn'}" style="margin:6px 0">${esc(e.mark)} <span class="small">This mark is included in every export.</span></div>` : ''}
        ${e.risks.length ? `<div class="risk">${e.risks.map(r => `<div>${badge(r.level, `${r.level} risk`)} ${esc(r.text)}</div>`).join('')}</div>` : `<div class="risk">${badge('Verified match', 'No risk flags')}</div>`}</div>`).join('')
        || empty('No citable sources yet. A source appears here once you accept it and its metadata is verified (or reviewed with a reason).')}
      ${bib.excluded.length ? `<details style="margin-top:10px"><summary>${bib.excluded.length} source(s) left out, and why</summary>${bib.excluded.map(x => `<p class="small">• ${badge(x.status || 'Pending review')} ${esc(x.title)}: ${esc(x.why)}</p>`).join('')}</details>` : ''}`,
      '', 'Citation Risk Review flags items that need a human look. It is not a probability that a reference is true.')
    + panel('AI-use disclosure', `<p class="small">${disc.saved ? 'Your edited wording.' : 'Built from this project\'s audit trail: what was searched, verified and checked, and every recorded AI call.'} It is added to every exported reference list.</p>
      <label for="disclosure" class="sr-only">AI-use disclosure</label><textarea id="disclosure" rows="6">${esc(disc.text)}</textarea>
      <div class="row" style="margin-top:8px"><button class="ghost small" data-action="cite-save-disclosure">Save wording</button>${disc.saved ? '<button class="ghost small" data-action="cite-reset-disclosure">Use generated version</button>' : ''}<button class="ghost small" data-action="cite-copy-disclosure">Copy</button>
        <span class="small muted">Adapt it to how you actually used the tool and to your institution's policy.</span></div>`, '', 'Blueprint integrity note: do not conceal AI involvement.');
}

export function after() {
  document.querySelectorAll('a[data-export]').forEach(a => a.addEventListener('click', () => setTimeout(renderApp, 800)));
}

export const actions = {
  'cite-style': (el, value) => { style = value; renderApp(); },
  'cite-copy': el => copyText(current.entries[Number(el.dataset.i)].text),
  'cite-copy-all': () => copyText(current.entries.map(e => e.text).join('\n\n')),
  'cite-save-disclosure': async () => {
    await api.put(`/projects/${state.projectId}/disclosure`, { text: document.getElementById('disclosure').value });
    toast('Disclosure saved. It will be included in exports.');
    renderApp();
  },
  'cite-reset-disclosure': async () => {
    await api.put(`/projects/${state.projectId}/disclosure`, { text: '' });
    toast('Using the generated disclosure.');
    renderApp();
  },
  'cite-copy-disclosure': () => copyText(document.getElementById('disclosure').value),
};
