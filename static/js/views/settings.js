// Settings: display name, service status, demo data and backups.
import { api } from '../api.js';
import { ask, badge, esc, heading, panel, toast } from '../ui.js';
import { render as renderApp, state } from '../main.js';

export async function render() {
  const s = state.status = await api.get('/status');
  const row = (ok, label, help) => `<div class="lineitem"><div><h3>${esc(label)}</h3><p>${help}</p></div>${badge(ok ? 'Verified match' : 'Pending review', ok ? 'Configured' : 'Not configured')}</div>`;
  return heading('Workspace preferences', 'Settings', 'Secrets live in the <code>.env</code> file next to <code>server.py</code> and never reach the browser. Restart the server after editing it.')
    + `<div class="grid">`
    + panel('You', `<form data-submit="settings-save" class="stack"><div class="field"><label for="s_name">Display name</label><input id="s_name" name="name" value="${esc(s.name)}" maxlength="80"></div><button type="submit" class="ghost">Save</button></form>`)
    + panel('Services', row(true, 'OpenAlex + Crossref', 'Live discovery and verification. Free; no key needed.')
      + row(s.ai, `Language model${s.model ? ` (${esc(s.model)})` : ''}`, 'Set <code>OPENAI_API_KEY</code> to enable AI planning, Red Team stance reading, challenge questions and synthesis. Everything works without it using rule-based methods.')
      + row(s.contact_email, 'Contact email for API “polite pool”', 'Optional <code>CONTACT_EMAIL</code>: OpenAlex and Crossref give faster, more reliable service to clients that identify themselves.')
      + row(s.openalex_key, 'OpenAlex API key', 'Optional <code>OPENALEX_API_KEY</code> if OpenAlex rate-limits you.'))
    + `</div>`
    + panel('AI features', `
      <p>${s.ai ? `<b>On</b> (${esc(s.model)}).` : s.ai_key ? '<b>Off.</b> An OpenAI key is set, but nothing is sent until you turn AI on.' : '<b>Off.</b> No <code>OPENAI_API_KEY</code> in <code>.env</code>; every feature uses rule-based methods.'}</p>
      <div class="notice"><b>When AI is on, this is sent to OpenAI:</b> your research question, claims, source titles and abstracts, and the passages you linked.
        <b>Never sent:</b> whole PDFs, your name, your email address. Every AI call is recorded in the Audit Trail with the model and prompt version, and every AI output is labelled.</div>
      <div class="row" style="margin-top:8px">${s.ai ? '<button class="ghost" data-action="ai-toggle" data-on="0">Turn AI off</button>'
        : s.ai_key ? '<button data-action="ai-toggle" data-on="1">Turn AI on</button>' : ''}
        <button class="link small" data-action="go" data-page="governance">AI-use policy →</button></div>`)
    + panel('Demo data', `<p>The sample project is synthetic and labelled everywhere. It is excluded from metrics and can never be cited.</p>
      <div class="row" style="margin-top:10px"><button class="ghost" data-action="demo-reset">Reload sample project</button>${s.demo_projects ? '<button class="danger" data-action="demo-remove">Remove demo data</button>' : ''}</div>`)
    + panel('Backups', `<p>Your work is stored in <code>data/veritas.db</code> on this computer. Download a JSON backup before sharing a machine or reinstalling.</p>
      <div class="row" style="margin-top:10px"><a href="/api/backup" download>Download backup (JSON)</a></div>`)
    + panel('Limits of this prototype', `<ul>
      <li>Single local user, no login. Keep the server bound to 127.0.0.1.</li>
      <li>Discovery covers OpenAlex only; “not found” means not found in Crossref and OpenAlex, not that a work does not exist.</li>
      <li>Venue tiers use journal citation metrics (or <code>data/journal_list.csv</code> if you add one). They are a screening aid, not a verdict on a paper.</li>
      <li>Passage matching shows that a source contains the words; it does not prove the source's study is correct.</li>
      <li>PDF text extraction needs text PDFs; scanned PDFs (OCR) are not supported. Page numbers are PDF file positions.</li>
      <li>Version ${esc(s.version)}.</li></ul>
      <p class="small" style="margin-top:8px"><button class="link small" data-action="go" data-page="governance">Risks, responses and data policy in Trust & Governance →</button></p>`);
}

export const actions = {
  'settings-save': async (form, data) => { await api.put('/settings', data); state.status = null; toast('Saved.'); renderApp(); },
  'ai-toggle': async el => {
    const on = el.dataset.on === '1';
    if (on && !await ask({ title: 'Turn on AI features?', message: 'Your research question, claims, source titles and abstracts, and linked passages will be sent to OpenAI when you use AI planning, the Red Team, the summary or the research assistant. Whole PDFs, your name and your email are never sent. You can turn this off at any time.', confirm: 'Turn AI on' })) return;
    await api.put('/settings/ai', { enabled: on });
    state.status = null;
    toast(on ? 'AI features on. Every call is logged in the Audit Trail.' : 'AI features off. Rule-based methods are used.');
    renderApp();
  },
  'demo-reset': async () => { await api.post('/demo/reset'); toast('Sample project reloaded.'); renderApp(); },
  'demo-remove': async () => {
    if (!await ask({ title: 'Remove demo data?', message: 'The sample project and its synthetic sources and claims are deleted. You can reload it later.', confirm: 'Remove', danger: true })) return;
    await api.del('/demo');
    toast('Demo data removed.');
    renderApp();
  },
};
