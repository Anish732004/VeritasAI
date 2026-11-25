// Trust & Governance: ethics risk register, accountability, AI-use and data policy, guardrails.
// All content comes from backend/governance.py, so the page shows the policy the code follows.
import { api } from '../api.js';
import { esc, heading, panel } from '../ui.js';
import { state } from '../main.js';

const PAGE_LABEL = {
  verification: 'Verification Centre', evidence: 'Evidence Graph', radar: 'Contradiction Radar', citations: 'Citation Studio',
  audit: 'Audit Trail', settings: 'Settings', studio: 'Research Studio', overview: 'Overview',
};
const show = page => `<button class="link small" data-action="go" data-page="${esc(page)}">${esc(PAGE_LABEL[page] || page)} →</button>`;
const statusBadge = s => s === 'In place'
  ? '<span class="badge good"><span aria-hidden="true">✓</span>In place</span>'
  : '<span class="badge warn" title="Mitigated, with a limit stated in the response"><span aria-hidden="true">◐</span>Partly</span>';

export async function render() {
  const g = await api.get('/governance');
  const s = state.status || {};
  const aiState = s.ai ? `On (${esc(s.model)})` : s.ai_key ? 'Off: key set, not turned on' : 'Off: no key';

  return heading('Ethics, accountability and safeguards', 'Trust & Governance',
    'How VERITAS handles the risks of AI-assisted research: who is accountable, what the AI may and may not do, what happens to your data, and the mechanisms that stop invented references and false claims.')
    + `<div class="metrics">${g.checks.map(c => `<div class="metric"><small>${esc(c.label)}</small><strong>${c.value}</strong><small>${esc(c.help || 'Real projects only')}</small></div>`).join('')}</div>`
    + panel('Principles', `<div class="cols3">${g.principles.map(([t, d]) => `<div><h3>${esc(t)}</h3><p class="small">${esc(d)}</p></div>`).join('')}</div>`)
    + panel('Ethical risks and our response to each', `<div style="overflow-x:auto"><table class="compare gov">
        <thead><tr><th scope="col">Risk</th><th scope="col">Response</th><th scope="col">Status</th><th scope="col">See it</th></tr></thead>
        <tbody>${g.risks.map(r => `<tr><td><b>${esc(r.risk)}</b>${r.source === 'Added' ? '<div class="small muted">Beyond the blueprint</div>' : ''}</td><td>${esc(r.response)}</td><td>${statusBadge(r.status)}</td><td>${show(r.where)}</td></tr>`).join('')}</tbody></table></div>`,
      '', 'The blueprint\'s risks (section 11), plus risks it does not list. "Partly" means the risk is reduced and the remaining limit is stated.')
    + `<div class="grid">`
    + panel('Accountability', g.accountability.map(([who, role, what]) => `<div class="lineitem"><div><h3>${esc(who)} <span class="badge info">${esc(role)}</span></h3><p>${esc(what)}</p></div></div>`).join(''))
    + panel('AI-use policy', `<p class="small">AI features: <b>${aiState}</b>. Prompt version ${esc(g.prompt_version)}.</p>
        <h4 style="margin:12px 0 6px">The language model may</h4><ul>${g.ai_may.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 style="margin:12px 0 6px">The language model may not</h4><ul>${g.ai_may_not.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <details style="margin-top:10px"><summary>Instructions sent with every AI request</summary><div class="quote">${esc(g.model_instructions)}</div></details>
        <p class="small" style="margin-top:10px"><b>Disclosure:</b> Citation Studio builds an AI-use disclosure from the audit trail of each project and adds it to every exported reference list. ${show('citations')}</p>`)
    + `</div>`
    + panel('Guardrails against invented references and false claims', g.guardrails.map(([name, how, where]) => `<div class="lineitem"><div><h3>${esc(name)}</h3><p>${esc(how)}</p></div>${show(where)}</div>`).join(''),
      '', 'Each one is enforced by code and covered by the offline test suite (tests/test_logic.py).')
    + panel('Data and privacy', g.data.map(([t, d]) => `<div class="lineitem"><div><h3>${esc(t)}</h3><p>${esc(d)}</p></div></div>`).join(''))
    + `<p class="small muted">The same policy is in GOVERNANCE.md in the project folder. Where your institution's academic-integrity or AI policy differs, follow your institution.</p>`;
}

export const actions = {};
