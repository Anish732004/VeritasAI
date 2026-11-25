// Pieces shared by several screens: the workflow step bar and the "next action" strip.
import { esc } from '../ui.js';

export const STAGE_PAGE = {
  define: 'studio', plan: 'studio', discover: 'studio', verify: 'verification',
  evidence: 'evidence', challenge: 'radar', approve: 'citations', cite: 'citations',
};

export function stepBar(bundle) {
  if (!bundle) return '';
  const next = bundle.workflow.next?.key;
  return `<nav class="steps" aria-label="Research workflow">${bundle.workflow.stages.map((s, i) => `
    <button class="step ${s.done ? 'done' : ''} ${s.key === next ? 'next' : ''}" data-action="go" data-page="${STAGE_PAGE[s.key]}"
      ${s.key === next ? 'aria-current="step"' : ''}>
      <span class="num" aria-hidden="true">${s.done ? '✓' : i + 1}</span>${esc(s.label)}<span class="sr-only">${s.done ? ' (done)' : ''}: ${esc(s.hint)}</span>
    </button>`).join('')}</nav>`;
}

export function stepDots(workflow) {
  const next = workflow.next?.key;
  return `<div class="stepdots" aria-label="${workflow.stages.filter(s => s.done).length} of ${workflow.stages.length} steps done">${workflow.stages
    .map(s => `<i class="${s.done ? 'done' : s.key === next ? 'next' : ''}" title="${esc(s.label)}"></i>`).join('')}</div>`;
}

export function nextAction(bundle, currentPage) {
  const n = bundle?.workflow.next;
  if (!n) return `<div class="nextaction"><p><b>All steps complete.</b> Your bibliography has been exported and every decision is in the audit trail.</p></div>`;
  const page = STAGE_PAGE[n.key];
  const todo = bundle.workflow.todo;
  let detail = '';
  if (n.key === 'verify' && todo.verify.length) detail = ` Still to review: ${todo.verify.map(esc).slice(0, 2).join('; ')}${todo.verify.length > 2 ? '…' : ''}.`;
  return `<div class="nextaction"><p><b>Next: ${esc(n.label)}.</b> ${esc(n.hint)}${detail}</p>${page !== currentPage ? `<button class="small" data-action="go" data-page="${page}">Go to ${esc(n.label)} →</button>` : ''}</div>`;
}

export function projectHeader(bundle, eyebrow, title, desc, action = '') {
  return `<div class="heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p><b>${esc(bundle.project.title)}</b> · ${esc(bundle.project.question)}</p>${desc ? `<p>${desc}</p>` : ''}</div>${action ? `<div class="row">${action}</div>` : ''}</div>`
    + stepBar(bundle);
}
