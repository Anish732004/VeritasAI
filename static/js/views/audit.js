// Audit Trail: every material action, by the student or an agent, with AI provenance.
import { api, qs } from '../api.js';
import { badge, empty, esc, fmtDate, heading, panel } from '../ui.js';
import { render as renderApp, state } from '../main.js';

let scope = 'project';

export async function render() {
  const pid = scope === 'project' ? state.projectId : '';
  const data = await api.get('/audit' + qs({ project: pid }));
  const rows = data.events.map(e => `<tr><td class="small">${fmtDate(e.created_at)}</td><td><b>${esc(e.action)}</b></td>
    <td class="small">${esc(e.details || '')}${e.ai?.model ? `<div class="mono">AI: ${esc(e.ai.model)} · prompt ${esc(e.ai.prompt_version)}${e.ai.inputs?.length ? ` · inputs ${esc(e.ai.inputs.slice(0, 5).join(', '))}` : ''}</div>` : ''}</td>
    <td class="small">${esc(e.actor)}</td></tr>`).join('');
  const runs = data.agent_runs.map(r => `<tr><td class="small">${fmtDate(r.started_at)}</td><td>${esc(r.agent)}</td><td>${badge(r.status === 'done' ? 'Accepted' : r.status === 'failed' ? 'Rejected' : 'Pending', r.status)}</td><td class="small">${esc(r.output_summary || r.error || '')}</td></tr>`).join('');
  return heading('Transparency by design', 'Audit Trail', 'Who did what, when, and with which model. Agents are listed by name; your decisions are listed as Student.',
    `<select data-change="audit-scope" aria-label="Scope"><option value="project" ${scope === 'project' ? 'selected' : ''}>This project</option><option value="all" ${scope === 'all' ? 'selected' : ''}>All projects</option></select>
     <a href="/api/backup" download>Download full backup</a>`)
    + panel('Decision trail', rows ? `<div class="tablewrap"><table><thead><tr><th>When</th><th>Action</th><th>Details</th><th>By</th></tr></thead><tbody>${rows}</tbody></table></div>` : empty('Actions appear here as you work.'))
    + panel('Agent runs', runs ? `<div class="tablewrap"><table><thead><tr><th>Started</th><th>Agent</th><th>Status</th><th>Output</th></tr></thead><tbody>${runs}</tbody></table></div>` : empty('No agent runs yet.'),
      '', 'Each agent has one narrow job. Retrieval and verification are deterministic; a language model, when configured, is used only for planning, critique and synthesis.')
    + `<p class="small muted">The log is stored in the local database. It is a record for you and your supervisor, not a tamper-proof ledger.</p>`;
}

export const actions = {
  'audit-scope': (el, value) => { scope = value; renderApp(); },
};
