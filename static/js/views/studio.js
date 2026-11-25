// Research Studio: Define → Plan (concept map, approval checkpoint) → Discover → Ask.
import { api } from '../api.js';
import { $, ask, badge, busy, empty, esc, panel, tierBadge, toast, authorsText, loading, errorBox, fmtDate } from '../ui.js';
import { state, render as renderApp, loadBundle } from '../main.js';
import { projectHeader, nextAction } from './common.js';

let lastSearch = { projectId: null, data: null, saved: {} };

const quote = t => (/[\s-]/.test(t) ? `"${t.replace(/"/g, '')}"` : t);
function queryPreview(groups) {
  const req = groups.filter(g => g.required);
  return (req.length ? req : groups.slice(0, 1)).map(g => '(' + g.terms.slice(0, 10).map(quote).join(' OR ') + ')').join(' AND ');
}

function listEditor(name, label, items) {
  return `<div class="field"><label for="pl_${name}">${label} (one per line)</label><textarea id="pl_${name}" data-plan="${name}" style="min-height:80px">${esc((items || []).join('\n'))}</textarea></div>`;
}

function groupRow(g, i) {
  return `<div class="group" data-group="${i}">
    <input aria-label="Concept label" data-g="label" value="${esc(g.label)}">
    <input aria-label="Search terms for ${esc(g.label)}, comma separated" data-g="terms" value="${esc(g.terms.join(', '))}">
    <label class="check"><input type="checkbox" data-g="required" ${g.required ? 'checked' : ''}> Required</label>
    <button class="ghost small" data-action="plan-remove-group" data-i="${i}" aria-label="Remove ${esc(g.label)}">✕</button>
  </div>`;
}

function planEditor(p) {
  const plan = p.plan;
  const f = plan.filters || {};
  const opt = (v, cur, label = v) => `<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${label}</option>`;
  return `
    <p class="small">${badge(plan.generated_by?.startsWith('AI') ? 'AI interpretation' : 'Pending')} ${esc(plan.generated_by || '')}. Edit anything, then approve. Nothing is searched until you approve.</p>
    ${plan.for_question && plan.for_question.trim() !== p.question.trim() ? `<div class="notice warn"><b>The question changed after this plan was made.</b> This plan is for “${esc(plan.for_question)}”. Click <b>Regenerate</b> to plan for the current question; approving is blocked until you do.</div>` : ''}
    ${plan.ai_note ? `<div class="notice"><b>How the question was understood:</b> ${esc(plan.ai_note)} <span class="muted">If this is not what you mean, edit the question and regenerate.</span></div>` : ''}
    ${!plan.generated_by?.startsWith('AI') && state.status?.ai_key && !state.status?.ai ? `<div class="notice warn">This plan used simple word rules. An OpenAI key is set, but AI is off. <button class="link" data-action="go" data-page="settings">Turn AI on in Settings</button> for a plan that understands the question, then Regenerate.</div>` : ''}
    ${!plan.generated_by?.startsWith('AI') && !state.status?.ai_key ? `<p class="small muted">This plan used simple word rules, which can miss the meaning of unusual topics. Add an OpenAI key (see Settings) for better concept maps, or edit the concepts below.</p>` : ''}
    <h4 style="margin:16px 0 8px">Concept map → search terms</h4>
    <p class="small">Every <b>required</b> concept must appear in a paper's title or abstract. Optional concepts only raise the ranking.</p>
    <div id="groups" style="margin-top:10px">${plan.concept_groups.map(groupRow).join('')}</div>
    <div class="row" style="margin-top:8px"><button class="ghost small" data-action="plan-add-group">＋ Add concept</button></div>
    <h4 style="margin:16px 0 8px">Filters</h4>
    <div class="row">
      <div class="field"><label for="f_years">Published in the last</label><select id="f_years" data-f="years">${[2, 3, 5, 10, 20].map(y => opt(y, f.years ?? 5, `${y} years`)).join('')}</select></div>
      <div class="field"><label for="f_tier">Minimum venue tier</label><select id="f_tier" data-f="min_tier">${opt('A', f.min_tier, 'A (top venues)')}${opt('B', f.min_tier ?? 'B', 'B (established venues)')}${opt('C', f.min_tier, 'C (any venue)')}</select></div>
      <div class="field"><label for="f_lang">Language</label><select id="f_lang" data-f="language">${opt('en', f.language ?? 'en', 'English')}${opt('', f.language, 'Any')}</select></div>
      <label class="check" style="margin-top:18px"><input type="checkbox" data-f="article_only" ${f.article_only !== false ? 'checked' : ''}> Journal articles</label>
      <label class="check" style="margin-top:18px" title="Adds papers presented at conferences. Their venue tier comes from a ranked list you add, or else from the publisher and the conference series' record."><input type="checkbox" data-f="include_conferences" ${f.include_conferences !== false ? 'checked' : ''}> Also conference papers</label>
      <label class="check" style="margin-top:18px"><input type="checkbox" data-f="include_foundational" ${f.include_foundational ? 'checked' : ''}> Add up to 5 highly cited older works</label>
    </div>
    <p class="small muted" style="margin-top:6px">Venue tiers come from citation metrics, which favour large, older, English-language venues. Conference papers are tiered from a ranked list you add (such as CORE), or else from the publisher and the conference series' record. Choose tier C or any language if relevant work is being filtered out (see README). <button class="link small" data-action="go" data-page="governance">Why this matters</button></p>
    <details><summary>Themes, sub-questions and inclusion criteria</summary>
      <div class="stack" style="margin-top:8px">${listEditor('themes', 'Themes', plan.themes)}${listEditor('subquestions', 'Sub-questions', plan.subquestions)}${listEditor('inclusion_criteria', 'Inclusion criteria', plan.inclusion_criteria)}</div>
    </details>
    <h4 style="margin:16px 0 8px">Query that will be sent to OpenAlex</h4>
    <div class="querybox" id="querybox">${esc(queryPreview(plan.concept_groups))}</div>
    <div class="row" style="margin-top:14px"><button data-action="plan-approve">Approve plan</button><button class="ghost" data-action="plan-save">Save draft</button><button class="ghost" data-action="plan-generate">Regenerate</button></div>`;
}

function planApproved(p) {
  const plan = p.plan, f = plan.filters || {};
  return `<div class="notice good">✓ Plan approved ${fmtDate(p.plan_approved_at)}. Reopen it to change the search.</div>
    <div class="stack">${plan.concept_groups.map(g => `<div><b>${esc(g.label)}</b> ${g.required ? badge('Accepted', 'Required') : '<span class="badge">Optional</span>'}
      <div class="row" style="margin-top:4px">${g.terms.map(t => `<span class="chip">${esc(t)}</span>`).join('')}</div></div>`).join('')}</div>
    <p class="small" style="margin-top:10px">Last ${esc(f.years)} years · venue tier ${esc(f.min_tier)} or higher · ${f.language ? 'English' : 'any language'} · ${f.article_only !== false ? (f.include_conferences !== false ? 'journal articles and conference papers' : 'journal articles only') : 'all work types'}${f.include_foundational ? ' · plus foundational works' : ''}</p>
    ${plan.subquestions?.length ? `<details><summary>Sub-questions and inclusion criteria</summary><ul>${plan.subquestions.map(s => `<li>${esc(s)}</li>`).join('')}</ul><ul>${(plan.inclusion_criteria || []).map(s => `<li>${esc(s)}</li>`).join('')}</ul></details>` : ''}
    <div class="row" style="margin-top:12px"><button class="ghost" data-action="plan-reopen">Reopen plan</button></div>`;
}

const REL_CLASS = { 3: 'good', 2: 'info', 1: 'warn', 0: 'bad' };
const REL_ICON = { 3: '●', 2: '◐', 1: '◔', 0: '○' };
function aiBlock(r) {
  const a = r.ai_relevance;
  if (!a) return '';
  return `<div class="airead"><span class="badge ${REL_CLASS[a.level]}" title="Rated by ${esc(a.model || 'the language model')} from the title and abstract only. A reading to help you decide, not a verdict."><span aria-hidden="true">${REL_ICON[a.level]}</span>AI: ${esc(a.label)}</span>
    ${a.reason ? `<span class="small"> ${esc(a.reason)}</span>` : ''}
    ${a.quote ? `<div class="quote small">“${esc(a.quote)}” <span class="muted">(found in the paper)</span></div>` : ''}</div>`;
}

function resultCard(r, i) {
  const saved = lastSearch.saved[i];
  const pct = Math.round((r.score?.total || 0) * 100);
  return `<article class="result">
    <div style="min-width:0">
      <h3>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}</h3>
      <p class="meta">${esc(authorsText(r.authors, 3))} · ${esc(r.year)} · <i>${esc(r.journal || 'Unknown venue')}</i></p>
      <div class="row" style="margin-top:6px">${r.kind === 'conference-paper' ? '<span class="badge info" title="Presented at a conference. Check how the conference reviewed papers (full papers or abstracts only)."><span aria-hidden="true">◈</span>Conference paper</span>' : ''}${tierBadge(r.venue)}${r.foundational ? '<span class="badge info">Foundational (older, highly cited)</span>' : ''}${r.abstract ? '' : '<span class="badge warn">No abstract</span>'}<span class="mono">${esc(r.doi || 'No DOI')}</span></div>
      <p class="why" style="margin-top:8px">Why it matched: ${esc(r.why)}</p>
      ${aiBlock(r)}
      ${r.abstract ? `<details><summary>Abstract</summary><p class="small">${esc(r.abstract)}</p></details>` : ''}
    </div>
    <div class="stack" style="justify-items:end;align-content:start">
      <div class="score" title="Coverage ${r.score.parts.coverage}, text ${r.score.parts.text}, venue ${r.score.parts.venue}, recency ${r.score.parts.recency}${r.score.parts.ai !== undefined ? `, AI relevance ${r.score.parts.ai} (half of the final score)` : ''}">Score <div class="bar"><i style="width:${pct}%"></i></div><b>${pct}</b></div>
      ${saved ? `<div>${badge(saved.verification_status)}</div><button class="ghost small" data-action="open-source" data-id="${esc(saved.id)}">Open</button>`
        : `<button class="small" data-action="save-result" data-i="${i}">＋ Save &amp; verify</button>`}
    </div>
  </article>`;
}

function resultsBlock() {
  const d = lastSearch.data;
  if (!d || lastSearch.projectId !== state.projectId) return empty('Approve the plan, then search. Results appear here with the reason each one matched.');
  const r = d.report;
  const removed = Object.entries(r.removed).filter(([, n]) => n).map(([k, n]) => `${n} ${k}`).join(' · ');
  const air = r.ai_relevance;
  const aiNote = air ? `<div class="notice">AI relevance check: <b>${air.rated}</b> papers rated against your question${air.off_topic ? `, <b>${air.off_topic}</b> rated likely off-topic and moved to the bottom (nothing was removed)` : ''}. Ratings are the model's reading of each title and abstract: check them against the papers. Half of each paper's score now comes from the rating.</div>`
    : r.ai_relevance_error ? `<div class="notice warn">The AI relevance check could not run: ${esc(r.ai_relevance_error)} Results are ranked by the standard score.</div>`
    : state.status?.ai ? '' : `<p class="small muted">Turn on AI in Settings to also rate how relevant each result is to your question.</p>`;
  return `${aiNote}${r.too_few ? `<div class="notice warn">${esc(r.too_few)}</div>` : ''}${r.relaxed ? `<div class="notice">${esc(r.relaxed)}</div>` : ''}
    ${d.results.map(resultCard).join('') || empty('No paper passed every filter. Widen the time window, lower the venue tier or make a concept optional.')}
    <p class="reportline muted"><b>${r.retrieved}</b> retrieved · <b>${r.shown}</b> shown${r.conference_papers ? ` (${r.conference_papers} conference)` : ''}${removed ? ' · removed: ' + esc(removed) : ''} · ${esc(r.window)} · tier ${esc(r.min_tier)}+</p>
    <details><summary>Search details</summary><div class="stack small" style="margin-top:6px">${r.queries.map(q => `<div class="querybox">${esc(q.query)}<br><span style="color:#8fa6d8">${q.count.toLocaleString()} matches in OpenAlex before filtering by concept and venue</span></div>`).join('')}
      <p class="mono">Filters: ${esc(r.filters.join(', '))}</p>${r.venue_warning ? `<p>${esc(r.venue_warning)}</p>` : ''}<p>${esc(r.note)}</p></div></details>`;
}

export async function render() {
  const b = state.bundle, p = b.project;
  const saved = b.references.filter(r => !r.demo);
  const chat = b.chat || [];
  return projectHeader(b, 'Human-in-the-loop workspace', 'Research Studio', 'Plan first. Discover second. Draw conclusions only after review.')
    + nextAction(b, 'studio')
    + `<div class="grid studio">
      ${panel('01 · Define the question', `<form data-submit="project-save" class="stack">
          <div class="field"><label for="d_q">Research question</label><textarea id="d_q" name="question" required minlength="5">${esc(p.question)}</textarea></div>
          <div class="formgrid"><div class="field"><label for="d_t">Title</label><input id="d_t" name="title" value="${esc(p.title)}"></div>
          <div class="field"><label for="d_s">Scope</label><input id="d_s" name="scope" value="${esc(p.scope || '')}" placeholder="Optional"></div></div>
          <div class="row"><button type="submit" class="ghost">Save question</button><span class="small muted">Changing the question reopens the plan.</span></div></form>
          <div class="row" style="margin-top:14px"><button class="danger small" data-action="project-delete">Delete project</button></div>`)}
      ${panel('02 · Plan and approve', p.plan ? (p.plan_approved_at ? planApproved(p) : planEditor(p))
        : `<p>VERITAS turns your question into concept groups and search terms${state.status?.ai ? ' using AI' : ' using transparent rules (no AI key configured)'}. You edit and approve them before anything is searched.</p>
           <button style="margin-top:12px" data-action="plan-generate">Generate proposed plan</button>`, p.plan_approved_at ? badge('Accepted', 'Approved') : '')}
    </div>
    ${panel('03 · Discover literature', `<div class="row"><button data-action="search" ${p.plan_approved_at ? '' : 'disabled'}>⌕ Search OpenAlex with the approved plan</button>
        ${p.plan_approved_at ? '' : '<span class="small muted">Checkpoint: approve the plan first.</span>'}
        <span class="small muted">${saved.length} source(s) saved in this project.</span>
        ${saved.length ? '<button class="ghost small" data-action="go" data-page="verification">Review verification →</button>' : ''}</div>
      <div id="results" style="margin-top:14px">${resultsBlock()}</div>`, '', 'Candidate sources only. A search result is not evidence for any claim, and saving runs a metadata check automatically.')}
    ${panel('04 · Research assistant', `<form data-submit="ask" class="row"><label for="askq" class="sr-only">Question</label><input id="askq" name="question" style="flex:1" required minlength="3" placeholder="Ask about gaps, methods or limitations in your saved sources" ${p.plan_approved_at ? '' : 'disabled'}><button type="submit" ${p.plan_approved_at ? '' : 'disabled'}>Ask</button></form>
      <div style="margin-top:10px">${chat.map(c => `<div class="card"><h3>${esc(c.question)}</h3><p class="small"><span class="badge ${c.ai?.model ? 'info' : ''}">${esc(c.ai?.label || '')}</span></p><p style="white-space:pre-wrap;margin-top:6px">${esc(c.answer)}</p></div>`).join('')}</div>`,
      '', 'Answers are reasoning to check, never evidence. Each one is recorded in the audit trail with the model used.')}`;
}

function collectPlan() {
  const p = state.bundle.project;
  const groups = [...document.querySelectorAll('#groups .group')].map(el => ({
    label: el.querySelector('[data-g=label]').value.trim(),
    terms: el.querySelector('[data-g=terms]').value.split(',').map(t => t.trim()).filter(Boolean),
    required: el.querySelector('[data-g=required]').checked,
  })).filter(g => g.terms.length);
  const filters = {};
  document.querySelectorAll('[data-f]').forEach(el => {
    filters[el.dataset.f] = el.type === 'checkbox' ? el.checked : (el.dataset.f === 'years' ? Number(el.value) : el.value);
  });
  const lines = n => ($(`pl_${n}`)?.value ?? (p.plan[n] || []).join('\n')).split('\n').map(s => s.trim()).filter(Boolean);
  return { concept_groups: groups, filters, themes: lines('themes'), subquestions: lines('subquestions'), inclusion_criteria: lines('inclusion_criteria') };
}

export function after() {
  const box = $('groups');
  if (box) box.addEventListener('input', () => { $('querybox').textContent = queryPreview(collectPlan().concept_groups); });
}

async function savePlan() {
  await api.put(`/projects/${state.projectId}/plan`, collectPlan());
}

export const actions = {
  'project-save': async (form, data) => {
    await api.patch(`/projects/${state.projectId}`, data);
    toast('Question saved.');
    renderApp();
  },
  'project-delete': async () => {
    const p = state.bundle.project;
    if (!await ask({ title: `Delete “${p.title}”?`, message: 'All of its sources, claims, evidence and chat are permanently deleted. The audit trail keeps a record that it was deleted. Download a backup first if unsure.', confirm: 'Delete project', danger: true })) return;
    await api.del(`/projects/${state.projectId}`);
    toast('Project deleted.');
    location.hash = 'overview';
  },
  'plan-generate': async el => {
    const done = busy(el, state.status?.ai ? 'Asking AI…' : 'Building plan…');
    try { await api.post(`/projects/${state.projectId}/plan`); } finally { done(); }
    toast('Plan proposed. Review and edit it before approving.');
    renderApp();
  },
  'plan-add-group': () => {
    const box = $('groups');
    box.insertAdjacentHTML('beforeend', groupRow({ label: 'New concept', terms: [], required: false }, box.children.length));
    box.lastElementChild.querySelector('[data-g=terms]').focus();
  },
  'plan-remove-group': el => { el.closest('.group').remove(); $('querybox').textContent = queryPreview(collectPlan().concept_groups); },
  'plan-save': async () => { await savePlan(); toast('Draft saved.'); renderApp(); },
  'plan-approve': async el => {
    const done = busy(el, 'Approving…');
    try {
      await savePlan();
      await api.post(`/projects/${state.projectId}/plan/approve`);
    } finally { done(); }
    toast('Plan approved. You can search now.');
    renderApp();
  },
  'plan-reopen': async () => { await api.post(`/projects/${state.projectId}/plan/reopen`); renderApp(); },
  'search': async el => {
    const done = busy(el, 'Searching OpenAlex…');
    $('results').innerHTML = loading('Querying OpenAlex, checking journal metrics and ranking results…');
    try {
      lastSearch = { projectId: state.projectId, data: await api.post(`/projects/${state.projectId}/search`), saved: {} };
      $('results').innerHTML = resultsBlock();
    } catch (e) {
      $('results').innerHTML = errorBox(e.message, 'search');
    } finally { done(); }
  },
  'save-result': async el => {
    const i = Number(el.dataset.i);
    const done = busy(el, 'Saving & verifying…');
    try {
      const ref = await api.post(`/projects/${state.projectId}/references`, { result: lastSearch.data.results[i] });
      lastSearch.saved[i] = ref;
      toast(`Saved. Metadata check: ${ref.verification_status}.`);
      await loadBundle();
      el.closest('.result').outerHTML = resultCard(lastSearch.data.results[i], i);
    } catch (e) {
      done();
      throw e;
    }
  },
  'ask': async (form, data) => {
    toast('Thinking…');
    await api.post(`/projects/${state.projectId}/ask`, data);
    renderApp();
  },
};

