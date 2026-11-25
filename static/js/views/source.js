// The source side panel: open any source from any screen without losing your place
// (blueprint UX rule). Also exports the field-by-field comparison table.
import { api } from '../api.js';
import { $, authorsInput, authorsText, badge, busy, closeDrawer, ask, closeModal, esc, fmtDate, openDrawer, openModal, tierBadge, toast } from '../ui.js';
import { render, state } from '../main.js';

const FIELD_LABEL = { title: 'Title', authors: 'Authors', year: 'Year', doi: 'DOI', journal: 'Journal' };
const FIELD_STATUS = {
  match: ['Verified match', 'Match'], partial: ['Partial match', 'Needs review'], mismatch: ['Mismatch', 'Conflict'],
  missing_supplied: ['Pending review', 'Missing in yours'], missing_database: ['Pending review', 'Missing in record'],
  missing_both: ['Pending', 'Not available'],
};

export function compareTable(v) {
  if (!v || !v.fields || !Object.keys(v.fields).length) return '';
  const provider = v.record?.provider || 'Database';
  return `<div class="tablewrap"><table class="compare stackable"><thead><tr><th>Field</th><th>Your reference</th><th>${esc(provider)} record</th><th>Result</th></tr></thead><tbody>
    ${Object.entries(v.fields).map(([k, f]) => {
      const [st, label] = FIELD_STATUS[f.status] || ['Pending', f.status];
      const cls = f.status === 'mismatch' ? 'mismatch' : f.status === 'partial' ? 'partial' : f.status.startsWith('missing') && f.status !== 'missing_both' ? 'missing' : '';
      return `<tr class="${cls}"><td>${FIELD_LABEL[k] || esc(k)}</td><td data-label="Your reference">${esc(f.supplied || '—')}</td><td data-label="${esc(provider)} record">${esc(f.database || '—')}</td><td data-label="Result">${badge(st, label)}<div class="small muted" style="margin-top:4px">${esc(f.note)}</div></td></tr>`;
    }).join('')}</tbody></table></div>
    <p class="small muted" style="margin-top:6px">Searched: ${esc((v.searched || []).join(', '))} · checked ${fmtDate(v.checked_at)}${v.record?.url ? ` · <a href="${esc(v.record.url)}" target="_blank" rel="noopener">open record</a>` : ''}</p>`;
}

export function resolveButtons(r) {
  const v = r.verification;
  const sugg = v?.suggestions && Object.keys(v.suggestions).length;
  if (r.demo) return '<span class="small muted">Demo sources cannot be verified.</span>';
  return `<button class="ghost small" data-action="ref-verify" data-id="${esc(r.id)}">↻ Re-check</button>
    ${sugg && r.verification_status !== 'Verified match' ? `<button class="soft small" data-action="ref-accept-db" data-id="${esc(r.id)}" title="Copy ${esc(Object.keys(v.suggestions).join(', '))} from the record">Use database values</button>` : ''}
    ${r.verification_status !== 'Verified match' && !r.override_reason && v ? `<button class="ghost small" data-action="ref-keep-mine" data-id="${esc(r.id)}">Keep mine (give reason)</button>` : ''}`;
}

export function decisionButtons(r, kind = 'ref') {
  return `<button class="ok small" data-action="${kind}-decide" data-id="${esc(r.id)}" data-d="Accepted" ${r.decision === 'Accepted' || r.demo ? 'disabled' : ''}>✓ Accept</button>
    <button class="danger small" data-action="${kind}-decide" data-id="${esc(r.id)}" data-d="Rejected" ${r.decision === 'Rejected' ? 'disabled' : ''}>✕ Reject</button>`;
}

async function refreshAfterChange(id) {
  await render();
  if (id && $('drawer').classList.contains('open')) await openSource(id);
}

export async function openSource(id) {
  const r = await api.get(`/references/${id}`);
  const v = r.verification;
  const disc = r.discovery || {};
  openDrawer(`
    <div class="eyebrow">Source record ${r.demo ? '· demo data' : ''}</div>
    <h2 style="margin-bottom:6px">${esc(r.title)}</h2>
    <p class="small">${esc(authorsText(r.authors, 8))} · ${esc(r.year || 'n.d.')} · <i>${esc(r.journal || 'No venue')}</i>${r.volume ? `, ${esc(r.volume)}` : ''}${r.issue ? `(${esc(r.issue)})` : ''}${r.pages ? `, ${esc(r.pages)}` : ''}</p>
    <p class="small">${r.doi ? `<a href="https://doi.org/${encodeURI(r.doi)}" target="_blank" rel="noopener">doi.org/${esc(r.doi)}</a>` : 'No DOI'} · from ${esc(r.metadata_source)}${r.retrieved_at ? ' · retrieved ' + fmtDate(r.retrieved_at) : ''}</p>
    <div class="row" style="margin:10px 0">${badge(r.verification_status)} ${badge(r.decision)} ${tierBadge(r.venue)} ${r.duplicates?.length ? '<span class="badge warn">Possible duplicate</span>' : ''}</div>
    ${v ? `<div class="notice ${r.verification_status === 'Verified match' ? 'good' : ['Mismatch', 'Not found'].includes(r.verification_status) ? 'bad' : 'warn'}">${esc(v.reason)}</div>` : '<div class="notice warn">Not checked yet.</div>'}
    ${r.override_reason ? `<div class="notice warn">You kept your own values: “${esc(r.override_reason)}”</div>` : ''}
    <div class="row">${resolveButtons(r)}</div>
    <div class="row" style="margin-top:8px">${decisionButtons(r)}<button class="ghost small" data-action="ref-delete" data-id="${esc(r.id)}">Delete</button></div>
    ${compareTable(v) ? `<h4 style="margin:18px 0 8px">Field comparison</h4>${compareTable(v)}` : ''}
    ${disc.why ? `<h4 style="margin:18px 0 8px">Why it was found</h4><p class="small">${esc(disc.why)}</p>` : ''}

    <h4 style="margin:18px 0 8px">Abstract</h4>
    ${r.abstract ? `<div class="quote" style="max-height:220px;overflow:auto">${esc(r.abstract)}</div>` : '<p class="small">No abstract stored. Evidence can still be checked against full text you attach.</p>'}

    <h4 style="margin:18px 0 8px">Full text</h4>
    ${r.has_fulltext ? `<p class="small">${badge('Accepted', 'Stored')} ${esc(r.fulltext_origin)} ${r.demo ? '' : `<button class="link small" data-action="ref-remove-text" data-id="${esc(r.id)}">Remove stored text</button>`}</p><details><summary>Preview</summary><div class="quote" style="max-height:220px;overflow:auto">${esc(r.fulltext_preview)}</div></details>`
      : '<p class="small">Not stored. Attach a PDF or text you are permitted to use so passages can be checked against it.</p>'}
    ${r.demo ? '' : '<p class="small muted">Only upload work you are allowed to use (open access, or through your library licence). The PDF file is not kept: only its text, stored on this computer and used to find passages. You can remove it at any time.</p>'}
    ${r.demo ? '' : `<div class="row" style="margin-top:8px">
      <label class="ghost small" style="border:1px solid var(--line);border-radius:7px;padding:6px 10px;cursor:pointer;color:var(--ink)">Upload PDF<input type="file" accept="application/pdf" data-change="ref-upload-pdf" data-id="${esc(r.id)}" class="sr-only"></label>
      <button class="ghost small" data-action="ref-fetch-oa" data-id="${esc(r.id)}">Fetch open-access copy</button>
      <button class="ghost small" data-action="ref-paste-toggle">Paste text</button></div>
      <form data-submit="ref-paste" data-id="${esc(r.id)}" id="pasteForm" hidden class="stack" style="margin-top:8px"><textarea name="text" minlength="50" required placeholder="Paste text you are allowed to use (at least 50 characters)"></textarea><button type="submit" class="small">Store text</button></form>`}

    <h4 style="margin:18px 0 8px">Organise</h4>
    <form data-submit="ref-organise" data-id="${esc(r.id)}" class="stack">
      <div class="formgrid"><div class="field"><label for="o_folder">Folder</label><input id="o_folder" name="folder" value="${esc(r.folder || '')}"></div>
      <div class="field"><label for="o_tags">Tags (comma separated)</label><input id="o_tags" name="tags" value="${esc((r.tags || []).join(', '))}"></div></div>
      <div class="field"><label for="o_notes">Notes</label><textarea id="o_notes" name="notes">${esc(r.notes || '')}</textarea></div>
      <button type="submit" class="ghost small">Save notes &amp; tags</button>
    </form>

    <details style="margin-top:14px"><summary>Edit bibliographic metadata (triggers a new check)</summary>
      <form data-submit="ref-edit" data-id="${esc(r.id)}" class="stack" style="margin-top:8px">${metadataFields(r)}<button type="submit" class="small">Save and re-check</button></form>
      ${r.original ? `<p class="small muted" style="margin-top:6px">Original values as first saved are kept: ${esc(r.original.title)} (${esc(r.original.year)}).</p>` : ''}
    </details>

    <h4 style="margin:18px 0 8px">Claims using this source</h4>
    ${r.claims?.length ? r.claims.map(c => `<p class="small">${badge(c.stance)} ${esc(c.text)} ${badge(c.status)}</p>`).join('') : '<p class="small">None yet.</p>'}
    ${r.history?.length > 1 ? `<h4 style="margin:18px 0 8px">Check history</h4>${r.history.map(h => `<p class="small">${fmtDate(h.checked_at)} · ${badge(h.status)}</p>`).join('')}` : ''}`);
}

export function metadataFields(r = {}) {
  const f = (k, label, val, extra = '') => `<div class="field ${extra}"><label for="m_${k}">${label}</label><input id="m_${k}" name="${k}" value="${esc(val ?? '')}"></div>`;
  return `<div class="formgrid">${f('title', 'Title', r.title, 'wide')}${f('authors', 'Authors (semicolon separated, “Given Family”)', authorsInput(r.authors), 'wide')}
    ${f('year', 'Year', r.year)}${f('doi', 'DOI', r.doi)}${f('journal', 'Journal', r.journal, 'wide')}${f('volume', 'Volume', r.volume)}${f('issue', 'Issue', r.issue)}${f('pages', 'Pages', r.pages)}${f('url', 'URL', r.url)}</div>`;
}


export const actions = {
  'open-source': el => openSource(el.dataset.id),
  'ref-verify': async el => {
    const done = busy(el, 'Checking…');
    try {
      const r = await api.post(`/references/${el.dataset.id}/verify`);
      toast(`Metadata check: ${r.verification_status}.`);
    } finally { done(); }
    await refreshAfterChange(el.dataset.id);
  },
  'ref-accept-db': async el => {
    const r = await api.post(`/references/${el.dataset.id}/resolve`, { action: 'accept_database' });
    toast(`Database values applied. New status: ${r.verification_status}.`);
    await refreshAfterChange(el.dataset.id);
  },
  'ref-keep-mine': async el => {
    const reason = await ask({ title: 'Keep your own values', message: 'Why are your values correct? For example: “checked the publisher page; the record lists the online-first year”. This is saved in the audit trail.', input: true, required: true, confirm: 'Keep my values' });
    if (!reason) return;
    await api.post(`/references/${el.dataset.id}/resolve`, { action: 'keep_mine', reason });
    toast('Your values were kept and the reason recorded.');
    await refreshAfterChange(el.dataset.id);
  },
  'ref-decide': async el => {
    let reason = '';
    if (el.dataset.d === 'Rejected') {
      reason = await ask({ title: 'Reject this source', message: 'Optional: why? (recorded in the audit trail)', input: true, confirm: 'Reject source', danger: true });
      if (reason === null) return;
    }
    await api.post(`/references/${el.dataset.id}/decision`, { decision: el.dataset.d, reason });
    toast(`Source ${el.dataset.d.toLowerCase()}.`);
    await refreshAfterChange(el.dataset.id);
  },
  'ref-delete': async el => {
    if (!await ask({ title: 'Delete this source?', message: 'Evidence linked to it is removed and those claims are re-assessed.', confirm: 'Delete', danger: true })) return;
    await api.del(`/references/${el.dataset.id}`);
    closeDrawer();
    toast('Source deleted.');
    render();
  },
  'ref-upload-pdf': async el => {
    const file = el.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    toast('Extracting text from PDF…');
    await api.upload(`/references/${el.dataset.id}/fulltext/pdf`, fd);
    toast('Full text stored. Linked passages were re-checked.');
    await refreshAfterChange(el.dataset.id);
  },
  'ref-fetch-oa': async el => {
    const done = busy(el, 'Downloading…');
    try { await api.post(`/references/${el.dataset.id}/fulltext/open-access`); } finally { done(); }
    toast('Open-access full text stored.');
    await refreshAfterChange(el.dataset.id);
  },
  'ref-remove-text': async el => {
    if (!await ask({ title: 'Remove stored text?', message: 'The full text is deleted from this computer. Passages that were only found in it will need the abstract or a new upload, and their claims are re-checked.', confirm: 'Remove', danger: true })) return;
    await api.del(`/references/${el.dataset.id}/fulltext`);
    toast('Stored text removed. Linked passages were re-checked.');
    await refreshAfterChange(el.dataset.id);
  },
  'ref-paste-toggle': () => { const f = $('pasteForm'); f.hidden = !f.hidden; },
  'ref-paste': async (form, data) => {
    await api.post(`/references/${form.dataset.id}/fulltext/text`, { text: data.text });
    toast('Text stored. Linked passages were re-checked.');
    await refreshAfterChange(form.dataset.id);
  },
  'ref-organise': async (form, data) => {
    await api.patch(`/references/${form.dataset.id}`, { folder: data.folder, notes: data.notes, tags: data.tags.split(',') });
    toast('Saved.');
    await refreshAfterChange(form.dataset.id);
  },
  'ref-edit': async (form, data) => {
    const r = await api.patch(`/references/${form.dataset.id}`, data);
    toast(`Saved. Metadata check: ${r.verification_status}.`);
    await refreshAfterChange(form.dataset.id);
  },
  'add-reference': () => openManual(),
  'manual-ref': async (form, data) => {
    const r = await api.post('/references', { ...data, project_id: data.project_id || state.projectId });
    closeModal();
    toast(`Added. Metadata check: ${r.verification_status}.`);
    await render();
    openSource(r.id);
  },
};

export function openManual() {
  openModal(`<h2 id="modalTitle">Check a reference</h2>
    <p class="small">Enter the details as you have them (for example from an AI answer or a reading list). VERITAS compares them with Crossref and OpenAlex and shows any differences. Nothing is corrected silently.</p>
    <form data-submit="manual-ref" class="stack" style="margin-top:12px">
      <div class="field"><label for="m_project">Project</label><select id="m_project" name="project_id">${state.projects.map(p => `<option value="${esc(p.id)}" ${p.id === state.projectId ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select></div>
      ${metadataFields()}
      <button type="submit">Add and check</button>
    </form>`);
}
