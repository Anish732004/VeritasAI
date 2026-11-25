// Settings: display name, service status, demo data and backups.
import { api } from '../api.js';
import { ask, badge, busy, esc, heading, panel, toast } from '../ui.js';
import { render as renderApp, state } from '../main.js';

// Step-by-step setup guide that shows how far you have got.
function aiSteps(s) {
  const step = (done, title, body) => `<li class="${done ? 'done' : ''}"><b>${done ? '✓ ' : ''}${title}</b><div class="small">${body}</div></li>`;
  if (s.ai) {
    return `<details style="margin:10px 0"><summary>Setup guide (all steps done)</summary><p class="small">To get a fresh AI plan for an existing project, open Research Studio and click <b>Regenerate</b>.</p></details>`;
  }
  return `<div style="margin:10px 0"><h4 style="margin-bottom:6px">Set up AI in five steps</h4>
    <ol class="steps-guide">
      ${step(s.ai_key, '1. Get an OpenAI API key', 'Sign in at <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">platform.openai.com/api-keys</a> and choose <b>Create new secret key</b>. Copy it straight away: it is shown only once. API use is billed separately from a ChatGPT subscription, so add a few dollars of credit under Billing (a full demo costs well under $1 with the default model).')}
      ${step(s.ai_key, '2. Put the key in <code>.env</code>', 'In the project folder, copy <code>.env.example</code> to <code>.env</code> (<code>cp .env.example .env</code>), open <code>.env</code> in any editor and write <code>OPENAI_API_KEY=sk-…</code> on one line, with no quotes or spaces. Never share the key or put it in chat, GitHub or a screenshot: <code>.env</code> is ignored by git for this reason.')}
      ${step(s.ai_key, '3. Restart the server', 'In the terminal running VERITAS press <b>Ctrl+C</b>, then start it again with <code>.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000</code>. The server reads <code>.env</code> only when it starts.')}
      ${step(false, '4. Test, then turn AI on', 'Come back to this page. Click <b>Test connection</b> (it sends no project data, only the word OK), then <b>Turn AI on</b> and read what is shared with OpenAI.')}
      ${step(false, '5. Regenerate your plan', 'Open <b>Research Studio</b>, and click <b>Regenerate</b> in the plan. You should see “AI proposal” and a line saying how your question was understood. Check the concepts, then approve.')}
    </ol></div>`;
}

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
      <p>${s.ai ? `<b>On</b> (${esc(s.model)}).` : s.ai_key ? '<b>Off.</b> An OpenAI key is set, but nothing is sent until you turn AI on.' : '<b>Off.</b> No <code>OPENAI_API_KEY</code> in <code>.env</code>; every feature uses rule-based methods.'}
        With AI on, Research Studio reads your question for meaning: it works out the concepts a paper must cover, adds the field's own terms and synonyms, and decides which concepts are essential. After a search it also rates how relevant each result is to your question, so the best papers rise to the top. You still edit and approve the plan, and nothing is ever removed or accepted for you.</p>
      ${aiSteps(s)}
      <div class="notice"><b>When AI is on, this is sent to OpenAI:</b> your research question and scope, claims, the titles and abstracts of sources and search results, and the passages you linked.
        <b>Never sent:</b> whole PDFs, your name, your email address. Every AI call is recorded in the Audit Trail with the model and prompt version, and every AI output is labelled.</div>
      <div class="row" style="margin-top:8px">${s.ai ? '<button class="ghost" data-action="ai-toggle" data-on="0">Turn AI off</button>'
        : s.ai_key ? '<button data-action="ai-toggle" data-on="1">Turn AI on</button>' : ''}
        ${s.ai_key ? '<button class="ghost" data-action="ai-test">Test connection</button>' : ''}
        <button class="link small" data-action="go" data-page="governance">AI-use policy →</button></div>`)
    + panel('Demo data', `<p>The sample project is synthetic and labelled everywhere. It is excluded from metrics and can never be cited.</p>
      <div class="row" style="margin-top:10px"><button class="ghost" data-action="demo-reset">Reload sample project</button>${s.demo_projects ? '<button class="danger" data-action="demo-remove">Remove demo data</button>' : ''}</div>`)
    + panel('Backups', `<p>Your work is stored in <code>data/veritas.db</code> on this computer. Download a JSON backup before sharing a machine or reinstalling.</p>
      <div class="row" style="margin-top:10px"><a href="/api/backup" download>Download backup (JSON)</a></div>
      <h4 style="margin:14px 0 6px">Restore from a backup</h4>
      <p class="small">Adds the projects, sources, claims, evidence, decisions and audit history from a backup file made here. Projects that already exist are left untouched (so restoring twice is safe), the sample project is not restored, and AI stays as you set it on this computer.</p>
      <div class="row" style="margin-top:8px"><label class="ghost" style="border:1px solid var(--line);border-radius:7px;padding:9px 13px;cursor:pointer">Choose backup file<input type="file" accept="application/json" class="sr-only" data-change="restore-backup"></label></div>`)
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
  'restore-backup': async el => {
    const file = el.files?.[0];
    if (!file) return;
    let data;
    try { data = JSON.parse(await file.text()); } catch { throw new Error('That file is not valid JSON.'); }
    const r = await api.post('/restore', data);
    const left = Object.entries(r.skipped).filter(([, n]) => n).map(([k, n]) => `${n} ${k}`).join(', ');
    toast(`Restored ${r.projects} project(s), ${r.references} source(s), ${r.claims} claim(s), ${r.evidence} evidence link(s).${left ? ` Left alone: ${left}.` : ''}`);
    state.status = null;
    renderApp();
  },
  'ai-test': async el => {
    const done = busy(el, 'Testing…');
    try {
      const r = await api.post('/settings/ai/test');
      toast(`Connected to OpenAI (${r.model}). Now turn AI on.`);
    } finally { done(); }
  },
  'ai-toggle': async el => {
    const on = el.dataset.on === '1';
    if (on && !await ask({ title: 'Turn on AI features?', message: 'Your research question and scope, claims, the titles and abstracts of sources and search results, and linked passages will be sent to OpenAI when you use AI planning, search-result relevance checks, the Red Team, the summary or the research assistant. Whole PDFs, your name and your email are never sent. You can turn this off at any time.', confirm: 'Turn AI on' })) return;
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
