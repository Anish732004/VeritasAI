// Research Library: where are my sources and what do I think of them? Works across projects.
import { api, qs } from '../api.js';
import { authorsText, badge, empty, esc, heading, panel, tierBadge, toast } from '../ui.js';
import { render as renderApp, state } from '../main.js';

const view = { q: '', project: '', status: '', tag: '', folder: '' };

function item(r) {
  return `<article class="card">
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div style="flex:1;min-width:0">
        <h3><button class="link" data-action="open-source" data-id="${esc(r.id)}">${esc(r.title)}</button></h3>
        <p class="meta">${esc(authorsText(r.authors, 3))} · ${esc(r.year || 'n.d.')} · <i>${esc(r.journal || '')}</i> · ${esc(r.project_title)}</p>
        <div class="row" style="margin-top:6px">${badge(r.verification_status)} ${badge(r.decision)} ${tierBadge(r.venue)} ${r.demo ? badge('Demo only') : ''}
          ${r.duplicates?.length ? `<span class="badge warn" title="Same DOI or title appears ${r.duplicates.length} more time(s)">⚠ Duplicate ×${r.duplicates.length + 1}</span>` : ''}
          ${r.has_fulltext ? '<span class="badge info">Full text stored</span>' : r.abstract ? '<span class="badge">Abstract only</span>' : '<span class="badge warn">No text</span>'}
          <span class="badge">${r.claim_count} claim(s)</span></div>
        ${(r.tags || []).length ? `<div class="row" style="margin-top:6px">${r.tags.map(t => `<button class="chip" data-action="lib-tag" data-tag="${esc(t)}">#${esc(t)}</button>`).join('')}</div>` : ''}
        ${r.notes ? `<p class="small" style="margin-top:6px">📝 ${esc(r.notes.slice(0, 220))}${r.notes.length > 220 ? '…' : ''}</p>` : ''}
      </div>
      <button class="ghost small" data-action="open-source" data-id="${esc(r.id)}">Open</button>
    </div>
  </article>`;
}

export async function render() {
  const refs = await api.get('/references' + qs({ q: view.q, project: view.project, status: view.status }));
  const allTags = [...new Set(refs.flatMap(r => r.tags || []))].sort();
  const folders = [...new Set(refs.map(r => r.folder || 'Unfiled'))].sort();
  let shown = refs.filter(r => (!view.tag || (r.tags || []).includes(view.tag)) && (!view.folder || (r.folder || 'Unfiled') === view.folder));
  const groups = {};
  shown.forEach(r => (groups[r.folder || 'Unfiled'] ??= []).push(r));
  const dupes = refs.filter(r => r.duplicates?.length).length;

  return heading('Your knowledge collection', 'Research Library', 'Organise sources across projects: folders, tags, notes, full text and duplicate alerts. Verification work happens in the Verification Centre.',
    '<button data-action="add-reference">＋ Paste or add sources</button><a href="/api/backup" class="small" download>Download backup (JSON)</a>')
    + `<section class="panel">
      <form data-submit="lib-filter" class="row">
        <label class="sr-only" for="lib_q">Search</label><input id="lib_q" name="q" value="${esc(view.q)}" placeholder="Search title, author, DOI, notes, tags" style="flex:1;min-width:220px">
        <label class="sr-only" for="lib_p">Project</label><select id="lib_p" name="project"><option value="">All projects</option>${state.projects.map(p => `<option value="${esc(p.id)}" ${view.project === p.id ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select>
        <label class="sr-only" for="lib_s">Status</label><select id="lib_s" name="status"><option value="">Any status</option>${['Verified match', 'Partial match', 'Mismatch', 'Not found', 'Pending review'].map(s => `<option ${view.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select>
        <label class="sr-only" for="lib_f">Folder</label><select id="lib_f" name="folder"><option value="">All folders</option>${folders.map(f => `<option ${view.folder === f ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>
        <button type="submit" class="ghost">Apply</button>
      </form>
      ${allTags.length ? `<div class="row" style="margin-top:10px"><span class="small muted">Tags:</span>${allTags.map(t => `<button class="chip" aria-pressed="${view.tag === t}" data-action="lib-tag" data-tag="${esc(t)}">#${esc(t)}</button>`).join('')}${view.tag ? '<button class="link small" data-action="lib-tag" data-tag="">clear</button>' : ''}</div>` : ''}
      ${dupes ? `<div class="notice warn">⚠ ${dupes} source(s) appear more than once (same DOI or title). Open them to compare and delete the extra copy.</div>` : ''}
    </section>`
    + (Object.entries(groups).map(([folder, list]) => panel(`📁 ${folder} (${list.length})`, list.map(item).join(''))).join('')
      || panel('Sources', empty(refs.length ? 'No source matches these filters.' : 'No sources yet. Search in Research Studio or add one manually.')))
    + panel('Import from the old version', `<p>If your team used the earlier browser-only VERITAS, export its workspace JSON (old Settings → Export) and import it here. Sources are re-checked against the databases.</p>
      <div class="row" style="margin-top:10px"><label class="ghost" style="border:1px solid var(--line);border-radius:7px;padding:9px 13px;cursor:pointer">Choose old workspace JSON<input type="file" accept="application/json" class="sr-only" data-change="lib-import"></label></div>`);
}

export const actions = {
  'lib-filter': (form, data) => { Object.assign(view, { q: data.q, project: data.project, status: data.status, folder: data.folder }); renderApp(); },
  'lib-tag': el => { view.tag = view.tag === el.dataset.tag ? '' : el.dataset.tag; renderApp(); },
  'lib-import': async el => {
    const file = el.files?.[0];
    if (!file) return;
    let data;
    try { data = JSON.parse(await file.text()); } catch { throw new Error('That file is not valid JSON.'); }
    const r = await api.post('/import/legacy', data);
    if (r.restored) { toast(`That was a VERITAS backup, so it was restored in full: ${r.projects} project(s), ${r.references} source(s), ${r.claims} claim(s).`); renderApp(); return; }
    toast(`Imported ${r.projects} project(s), ${r.references} source(s), ${r.claims} claim(s). Re-check sources in the Verification Centre.`);
    renderApp();
  },
};
