// Evidence Graph: claims, the passages behind them, and the evidence-backed summary.
import { api, qs } from '../api.js';
import { $, ask, badge, busy, closeModal, empty, esc, fmtDate, openModal, panel, toast } from '../ui.js';
import { render as renderApp, state } from '../main.js';
import { nextAction, projectHeader } from './common.js';

let suggestions = [];
const TYPE_LABEL = { source_finding: 'Source finding', ai_interpretation: 'AI interpretation / my reasoning' };
const STATUS_COLOR = {
  'Source-supported': ['#e1f4eb', '#11704f'], 'Contradicted / qualified': ['#fce9e7', '#a83c3a'],
  'Reported, not independently checked': ['#fff1d6', '#8f5a0c'], 'AI interpretation': ['#e7edff', '#2c4cb5'],
  'Not found': ['#fce9e7', '#a83c3a'], 'Demo only': ['#ece8fc', '#5b44a6'],
};

const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

function graph(b) {
  const refs = Object.fromEntries(b.references.map(r => [r.id, r]));
  const rowH = 74;
  let y = 20;
  const parts = [];
  const claimYs = [];
  b.claims.forEach((c, ci) => {
    const ev = c.evidence.length ? c.evidence : [null];
    const top = y, h = ev.length * rowH - 14;
    const cy = top + h / 2;
    claimYs.push(cy);
    const [bg, fg] = STATUS_COLOR[c.status] || ['#fff', '#203554'];
    parts.push(`<g role="button" tabindex="0" data-action="ev-focus" data-id="${esc(c.id)}" aria-label="Claim ${ci + 1}: ${esc(c.status)}">
      <rect x="200" y="${cy - 28}" width="200" height="56" rx="8" fill="${bg}" stroke="${fg}"/>
      <text x="212" y="${cy - 8}" font-size="12" font-weight="700" fill="#19273b">Claim ${ci + 1}: ${esc(trunc(c.text, 24))}</text>
      <text x="212" y="${cy + 12}" font-size="11" fill="${fg}">${esc(trunc(c.status, 32))}</text></g>`);
    ev.forEach((e, ei) => {
      const ey = top + ei * rowH + (rowH - 14) / 2;
      parts.push(`<path d="M400 ${cy} C430 ${cy},420 ${ey},450 ${ey}" stroke="#b1bdd3" fill="none"/>`);
      if (!e) {
        parts.push(`<rect x="450" y="${ey - 22}" width="170" height="44" rx="7" fill="#fbe5e5"/><text x="535" y="${ey + 4}" text-anchor="middle" font-size="11" fill="#a83c3a">No linked passage</text>`);
        return;
      }
      const r = refs[e.reference_id];
      const color = e.stance === 'supports' ? '#e5ebff' : '#fff1d6';
      parts.push(`<rect x="450" y="${ey - 22}" width="170" height="44" rx="7" fill="${color}"/>
        <text x="460" y="${ey - 4}" font-size="11" fill="#203554">${esc(e.stance)} · ${esc(e.match.replace('_', ' '))}</text>
        <text x="460" y="${ey + 12}" font-size="10" fill="#586b88">${esc(e.location || 'location unknown')}${e.page ? ' p.' + esc(e.page) : ''}</text>
        <path d="M620 ${ey}H660" stroke="#b1bdd3"/>`);
      if (r) {
        parts.push(`<g role="button" tabindex="0" data-action="open-source" data-id="${esc(r.id)}" aria-label="Open source ${esc(r.title)}">
          <rect x="660" y="${ey - 24}" width="230" height="48" rx="8" fill="#fff" stroke="#b1bdd3"/>
          <text x="670" y="${ey - 5}" font-size="11" fill="#203554">${esc(trunc(r.title, 34))}</text>
          <text x="670" y="${ey + 13}" font-size="10" fill="#586b88">${esc(r.year || '')} · ${esc(r.verification_status)}</text></g>`);
      }
    });
    y += ev.length * rowH + 8;
  });
  const h = Math.max(y, 140);
  const qy = h / 2;
  const lines = claimYs.map(cy => `<path d="M160 ${qy} C185 ${qy},175 ${cy},200 ${cy}" stroke="#b1bdd3" fill="none"/>`).join('');
  return `<div class="graph"><svg viewBox="0 0 900 ${h}" role="img" aria-label="Evidence lineage from question to claims, passages and sources">
    ${lines}<rect x="10" y="${qy - 34}" width="150" height="68" rx="10" fill="#182a49"/>
    <text x="85" y="${qy - 4}" fill="#fff" font-size="12" text-anchor="middle">Research</text><text x="85" y="${qy + 14}" fill="#b6caff" font-size="12" text-anchor="middle">question</text>
    ${parts.join('')}</svg></div>
    <p class="small muted" style="margin-top:8px">Question → claims → passages (stance · match · location) → sources. Select a claim or source to inspect it.</p>`;
}

function evidenceItem(e, refs) {
  const r = refs[e.reference_id];
  return `<div class="evidence ${esc(e.stance)}">
    <div class="row">${badge(e.stance)} ${badge(e.match)} <span class="small muted">${esc(e.location ? (e.location === 'abstract' ? 'Abstract' : 'Full text') : '')}${e.page ? ` · PDF page ${esc(e.page)} (file position)` : ''}${e.origin === 'red team' ? ' · from Red Team' : e.origin === 'suggested' ? ' · suggested passage' : ''}</span></div>
    <div class="quote" style="margin-top:6px">${esc(e.passage)}</div>
    <div class="row" style="margin-top:6px"><span class="small">Source: ${r ? `<button class="link small" data-action="open-source" data-id="${esc(r.id)}">${esc(r.title)}</button> ${badge(r.verification_status)}` : 'deleted'}</span>
      <button class="ghost small" data-action="ev-unlink" data-id="${esc(e.id)}">Unlink</button></div>
  </div>`;
}

function claimCard(c, i, refs) {
  return `<article class="card" id="claim-${esc(c.id)}">
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div style="flex:1;min-width:0"><span class="mono">DNA-${String(i + 1).padStart(3, '0')} · ${esc(TYPE_LABEL[c.claim_type] || c.claim_type)}</span>
        <h3 style="margin-top:4px">${esc(c.text)}</h3>
        <div class="row" style="margin-top:6px">${badge(c.status)} ${badge(c.decision)} ${c.evidence_level ? `<span class="badge">${esc(c.evidence_level)}</span>` : ''}</div>
        <p class="why-status"><b>Why this label:</b> ${esc(c.status_reason || '')}</p>
        ${c.decision_reason ? `<p class="small">Your decision note: “${esc(c.decision_reason)}”</p>` : ''}
      </div>
      <div class="row end">${c.demo ? '' : `<button class="small" data-action="ev-link" data-id="${esc(c.id)}">＋ Link evidence</button>`}</div>
    </div>
    ${c.evidence.map(e => evidenceItem(e, refs)).join('')}
    ${c.demo ? '' : `<div class="row" style="margin-top:12px">
      <button class="ok small" data-action="claim-decide" data-id="${esc(c.id)}" data-d="Accepted" ${c.decision === 'Accepted' ? 'disabled' : ''}>✓ Accept</button>
      <button class="danger small" data-action="claim-decide" data-id="${esc(c.id)}" data-d="Rejected" ${c.decision === 'Rejected' ? 'disabled' : ''}>✕ Reject</button>
      <button class="ghost small" data-action="claim-edit" data-id="${esc(c.id)}">Edit</button>
      <button class="ghost small" data-action="go" data-page="radar">Challenge →</button>
      <button class="ghost small" data-action="claim-delete" data-id="${esc(c.id)}">Delete</button></div>`}
  </article>`;
}

function summaryBlock(s) {
  if (!s) return empty('Build a summary once you have claims. Every sentence is either tied to a located passage or labelled as interpretation.');
  return `<p class="small muted">Built ${fmtDate(s.generated_at)}</p>
    ${s.synthesis ? `<h4 style="margin:12px 0 6px">Synthesis (${esc(s.synthesis.model)}, unverified)</h4>
      ${s.synthesis.sentences.map(x => `<p style="color:var(--ink);margin-top:6px">${esc(x.sentence)} ${x.claim_ids.length ? badge('Source-supported', 'Source-linked') : badge('AI interpretation')}</p>`).join('')}` : ''}
    ${s.synthesis_error ? `<div class="notice warn">AI synthesis unavailable: ${esc(s.synthesis_error)}</div>` : ''}
    ${s.sections.map(sec => `<h4 style="margin:16px 0 6px">${badge(sec.status)}</h4>${sec.items.map(it => `
      <div class="card"><p style="color:var(--ink)"><b>${esc(it.text)}</b> ${it.citations.map(c => `(${esc(c.ref)})`).join(' ')}</p>
        ${it.citations.map(c => `<div class="quote small" style="margin-top:6px">“${esc(c.passage)}” <span class="muted">— ${esc(c.ref)}, ${esc(c.location)}</span></div>`).join('')}
        ${it.counter.map(c => `<p class="small" style="margin-top:6px">${badge(c.stance)} “${esc(c.passage)}” — ${esc(c.ref)}</p>`).join('')}
        ${!it.citations.length ? `<p class="small">${esc(it.reason)}</p>` : ''}</div>`).join('')}`).join('')}`;
}

export async function render() {
  const b = state.bundle;
  const refs = Object.fromEntries(b.references.map(r => [r.id, r]));
  return projectHeader(b, 'Signature feature · Evidence DNA', 'Evidence Graph', 'Write claims, then link each one to a passage that actually exists in a source.',
    '<button data-action="claim-new">＋ Add claim</button>')
    + nextAction(b, 'evidence')
    + `<div class="notice">Labels follow the blueprint: <b>Source-supported</b> (passage located in source text), <b>Reported, not independently checked</b> (source text not stored), <b>AI interpretation</b>, <b>Not found</b>, <b>Contradicted / qualified</b>. A located passage shows the source says it; it does not prove the study is right.</div>`
    + panel('Evidence lineage', b.claims.length ? graph(b) : empty('No claims yet.'))
    + panel(`Claim register (${b.claims.length})`, b.claims.map((c, i) => claimCard(c, i, refs)).join('') || empty('Add your first claim. Example: “Personalised recommendations are associated with higher customer satisfaction.”'))
    + panel('Evidence-backed summary', `<div id="summary">${summaryBlock(b.project.summary)}</div>`, `<button class="ghost small" data-action="summary-build" ${b.claims.length ? '' : 'disabled'}>Build summary</button>`);
}

function linkModal(claim) {
  const refs = state.bundle.references.filter(r => r.decision !== 'Rejected');
  openModal(`<h2 id="modalTitle">Link evidence</h2><p class="small" style="margin-top:4px">Claim: <b>${esc(claim.text)}</b></p>
    <form data-submit="ev-save" data-id="${esc(claim.id)}" class="stack" style="margin-top:12px">
      <div class="field"><label for="ev_ref">Source</label><select id="ev_ref" name="reference_id" data-change="ev-source" data-claim="${esc(claim.id)}" required>
        <option value="">Choose a source…</option>${refs.map(r => `<option value="${esc(r.id)}">${esc(r.title.slice(0, 90))} (${esc(r.year || 'n.d.')}) · ${esc(r.verification_status)}</option>`).join('')}</select></div>
      <div id="ev_sugg"></div>
      <div class="field"><label for="ev_passage">Passage (copied from the source)</label><textarea id="ev_passage" name="passage" required minlength="10" placeholder="Pick a suggestion above or paste the exact sentence"></textarea></div>
      <div class="field"><label for="ev_stance">This passage…</label><select id="ev_stance" name="stance"><option value="supports">supports the claim</option><option value="qualifies">qualifies / limits the claim</option><option value="challenges">challenges the claim</option></select></div>
      <input type="hidden" name="origin" id="ev_origin" value="student">
      <button type="submit">Check passage and link</button>
    </form>`);
}

export const actions = {
  'claim-new': () => openModal(`<h2 id="modalTitle">Add a claim</h2>
    <form data-submit="claim-create" class="stack" style="margin-top:12px">
      <div class="field"><label for="cl_text">Claim</label><textarea id="cl_text" name="text" required minlength="5" placeholder="State one specific finding"></textarea></div>
      <div class="field"><label for="cl_type">Type</label><select id="cl_type" name="claim_type"><option value="source_finding">Source finding (I will link a passage)</option><option value="ai_interpretation">Interpretation / synthesis (mine or AI's)</option></select></div>
      <button type="submit">Add claim</button></form>`),
  'claim-create': async (form, data) => {
    const c = await api.post(`/projects/${state.projectId}/claims`, data);
    closeModal();
    await renderApp();
    if (c.claim_type === 'source_finding') { linkModal(c); }
  },
  'ev-focus': el => { $(`claim-${el.dataset.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); },
  'ev-link': el => linkModal(state.bundle.claims.find(c => c.id === el.dataset.id)),
  'ev-source': async (el, value) => {
    const box = $('ev_sugg');
    if (!value) { box.innerHTML = ''; return; }
    box.innerHTML = '<p class="loading small">Finding matching sentences in the stored text…</p>';
    const r = await api.get(`/claims/${el.dataset.claim}/suggest` + qs({ reference_id: value }));
    suggestions = r.suggestions;
    box.innerHTML = `<p class="small muted">${esc(r.note)}</p>` + suggestions.map((s, i) => `<div class="card"><div class="quote small">${esc(s.text)}</div>
      <div class="row" style="margin-top:6px"><span class="small muted">${esc(s.location_label)} · relevance ${s.score}</span><button type="button" class="soft small" data-action="ev-use" data-i="${i}">Use this passage</button></div></div>`).join('');
  },
  'ev-use': el => { $('ev_passage').value = suggestions[Number(el.dataset.i)].text; $('ev_origin').value = 'suggested'; },
  'ev-save': async (form, data) => {
    const r = await api.post(`/claims/${form.dataset.id}/evidence`, data);
    closeModal();
    const m = r.match.match;
    toast(m === 'exact' ? 'Passage found word for word in the source.' : m === 'near' ? 'Passage near-matched (formatting differences).'
      : m === 'no_text' ? 'Linked, but no source text is stored to check it against.' : 'Passage NOT found in the stored source text; the claim stays “Not found”.', m === 'not_located' ? 'bad' : '');
    renderApp();
  },
  'ev-unlink': async el => {
    if (!await ask({ title: 'Unlink this passage?', confirm: 'Unlink', danger: true })) return;
    await api.del(`/evidence/${el.dataset.id}`);
    renderApp();
  },
  'claim-decide': async el => {
    const c = state.bundle.claims.find(x => x.id === el.dataset.id);
    let reason = '';
    if (el.dataset.d === 'Rejected' || c.status === 'Not found') {
      const mustExplain = c.status === 'Not found' && el.dataset.d === 'Accepted';
      reason = await ask({ title: `${el.dataset.d === 'Accepted' ? 'Accept' : 'Reject'} claim`, input: true, required: mustExplain,
        message: mustExplain ? 'This claim has no located evidence. Why accept it anyway? (recorded in the audit trail)' : 'Optional: add a reason (recorded in the audit trail).',
        confirm: el.dataset.d === 'Accepted' ? 'Accept claim' : 'Reject claim', danger: el.dataset.d === 'Rejected' });
      if (reason === null) return;
    }
    await api.post(`/claims/${el.dataset.id}/decision`, { decision: el.dataset.d, reason });
    renderApp();
  },
  'claim-edit': el => {
    const c = state.bundle.claims.find(x => x.id === el.dataset.id);
    openModal(`<h2 id="modalTitle">Edit claim</h2><p class="small">Editing resets your decision to pending.</p>
      <form data-submit="claim-save" data-id="${esc(c.id)}" class="stack" style="margin-top:12px">
        <textarea name="text" aria-label="Claim" required minlength="5">${esc(c.text)}</textarea>
        <select name="claim_type" aria-label="Type">${Object.entries(TYPE_LABEL).map(([k, l]) => `<option value="${k}" ${c.claim_type === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <button type="submit">Save</button></form>`);
  },
  'claim-save': async (form, data) => { await api.patch(`/claims/${form.dataset.id}`, data); closeModal(); renderApp(); },
  'claim-delete': async el => {
    if (!await ask({ title: 'Delete this claim?', message: 'Its evidence links are removed too.', confirm: 'Delete', danger: true })) return;
    await api.del(`/claims/${el.dataset.id}`);
    renderApp();
  },
  'summary-build': async el => {
    const done = busy(el, 'Building…');
    try {
      const s = await api.post(`/projects/${state.projectId}/summary`);
      $('summary').innerHTML = summaryBlock(s);
    } finally { done(); }
  },
};
