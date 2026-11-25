// Contradiction Radar + Research Red Team: look for the other side of every claim.
import { api } from '../api.js';
import { $, authorsText, badge, busy, empty, errorBox, esc, loading, panel, toast } from '../ui.js';
import { render as renderApp, state } from '../main.js';
import { nextAction, projectHeader } from './common.js';

let selected = null;
let found = {}; // claimId -> challenge response

function resultCard(r, i, claimId) {
  return `<div class="card">
    <h3 style="font-size:14px">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}</h3>
    <p class="meta">${esc(authorsText(r.authors, 2))} · ${esc(r.year)} · <i>${esc(r.journal || '')}</i></p>
    <div class="quote small" style="margin-top:6px">“${esc(r.sentence)}”</div>
    <p class="small muted" style="margin-top:4px">${badge(r.stance)} read by: ${esc(r.stance_method)}</p>
    ${r.in_project ? '<p class="small">Already in this project.</p>' : ''}
    <div class="row" style="margin-top:6px">${['challenges', 'qualifies', 'supports'].map(s => `<button class="${s === 'supports' ? 'ghost' : 'soft'} small" data-action="radar-link" data-claim="${esc(claimId)}" data-i="${i}" data-stance="${s}">Link as ${s}</button>`).join('')}</div>
  </div>`;
}

function resultsBlock(claimId) {
  const d = found[claimId];
  if (!d) return empty('Run the Red Team to search OpenAlex for studies that qualify or challenge this claim.');
  const col = st => d.results.map((r, i) => [r, i]).filter(([r]) => r.stance === st);
  const colHTML = (title, st) => `<div><h4>${badge(st, title)}</h4>${col(st).map(([r, i]) => resultCard(r, i, claimId)).join('') || '<p class="small muted">None found.</p>'}</div>`;
  return `${d.alerts.length ? `<div class="notice warn"><b>Red Team checks</b><ul>${d.alerts.map(a => `<li><b>${esc(a.kind)}:</b> ${esc(a.detail)}</li>`).join('')}</ul></div>` : ''}
    ${d.questions?.length ? `<div class="notice"><b>${esc(d.questions_label)}</b><ul>${d.questions.map(q => `<li>${esc(q)}</li>`).join('')}</ul></div>` : ''}
    <div class="columns">${colHTML('Challenges', 'challenges')}${colHTML('Qualifies', 'qualifies')}${colHTML('Supports', 'supports')}</div>
    ${col('unclear').length ? `<details style="margin-top:10px"><summary>${col('unclear').length} result(s) with unclear stance</summary>${col('unclear').map(([r, i]) => resultCard(r, i, claimId)).join('')}</details>` : ''}
    <p class="small muted" style="margin-top:10px">${esc(d.note)} Stance labels are a reading aid: open the paper before relying on one.</p>
    <details><summary>Search query</summary><div class="querybox">${esc(d.query)}</div></details>`;
}

export async function render() {
  const b = state.bundle;
  const alerts = await api.get(`/projects/${state.projectId}/redteam`);
  const claims = b.claims.filter(c => !c.demo);
  if (!selected || !claims.some(c => c.id === selected)) selected = claims[0]?.id || null;
  const linkedCounter = claims.flatMap(c => c.evidence.filter(e => e.stance !== 'supports').map(e => ({ c, e })));

  return projectHeader(b, 'Adversarial research review', 'Contradiction Radar', 'Challenge your conclusions instead of collecting agreement.')
    + nextAction(b, 'radar')
    + panel('Red Team alerts across all claims', alerts.filter(a => a.alerts.length).map(a => `<div class="lineitem"><div><h3>${esc(a.claim.text)}</h3>
        <ul>${a.alerts.map(x => `<li><b>${esc(x.kind)}:</b> ${esc(x.detail)}</li>`).join('')}</ul></div>
        <button class="ghost small" data-action="radar-select" data-id="${esc(a.claim.id)}">Challenge</button></div>`).join('') || empty('No rule-based alerts. That is not the same as no problems: run a counter-evidence search below.'),
      '', 'Rule checks: universal wording, causal language on weak evidence, single source, unverified source, missing evidence, interpretation.')
    + (claims.length ? panel('Counter-evidence search', `
      <div class="row"><label for="radar_claim" class="sr-only">Claim</label><select id="radar_claim" data-change="radar-choose" style="flex:1;min-width:240px">
        ${claims.map(c => `<option value="${esc(c.id)}" ${c.id === selected ? 'selected' : ''}>${esc(c.text.slice(0, 120))} · ${esc(c.status)}</option>`).join('')}</select>
        <button data-action="radar-run">◎ Run Red Team</button></div>
      <div id="radar_results" style="margin-top:14px">${resultsBlock(selected)}</div>`) : empty('Claims from demo data cannot be challenged. Add your own claims in the Evidence Graph.'))
    + panel('Linked counter-evidence', linkedCounter.map(({ c, e }) => `<div class="lineitem"><div><p class="small"><b>${esc(c.text)}</b></p>
        <p class="small">${badge(e.stance)} “${esc(e.passage)}”</p></div>${badge(c.status)}</div>`).join('') || empty('Nothing linked yet. Linked passages turn a claim into “Contradicted / qualified” until you review it.'));
}

export const actions = {
  'radar-select': el => { selected = el.dataset.id; renderApp().then(() => $('radar_results')?.scrollIntoView({ behavior: 'smooth' })); },
  'radar-choose': (el, value) => { selected = value; $('radar_results').innerHTML = resultsBlock(selected); },
  'radar-run': async el => {
    const done = busy(el, 'Searching for counter-evidence…');
    $('radar_results').innerHTML = loading('Searching OpenAlex for studies that qualify or challenge this claim…');
    try {
      found[selected] = await api.post(`/claims/${selected}/challenge`);
      $('radar_results').innerHTML = resultsBlock(selected);
    } catch (e) {
      $('radar_results').innerHTML = errorBox(e.message, 'radar-run');
    } finally { done(); }
  },
  'radar-link': async el => {
    const d = found[el.dataset.claim];
    const r = d.results[Number(el.dataset.i)];
    await api.post(`/claims/${el.dataset.claim}/counter`, { result: r, sentence: r.sentence, stance: el.dataset.stance });
    toast(`Linked as ${el.dataset.stance}. The source was saved to the project and checked.`);
    await renderApp();
  },
};

