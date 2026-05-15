# SKILL.md — FIDPHA001 Execution Intelligence

> This file is not a rules document and not an architecture reference.
> CLAUDE.md owns rules. ARCHITECTURE.md owns structure.
> This file owns reasoning: how to think, decide, and execute correctly in this codebase.
> Read it before acting on any non-trivial task.

---

## 1. Purpose

Rules alone do not prevent bad implementations. A developer who knows all the rules can still:
- put logic in the wrong layer
- duplicate an existing service function
- build a screen-shaped API instead of a resource-shaped one
- fix a symptom instead of the source

This file closes that gap. It encodes the reasoning process behind correct execution — the thinking that precedes the typing.

---
## 1.1 Pre-Action Checklist (Run Before Any Change)

Before writing code, quickly confirm:

- What type of task is this? (bug / feature / API / UI / performance)
- What layer owns it?
- Does this already exist somewhere?
- What is the smallest possible change?
- What will break if I change this?

If any answer is unclear, stop and resolve it before proceeding.

## 2. Problem Decomposition

Before writing a single line, answer these questions in order. Do not skip ahead.

**Step 1 — Classify the request**

| Request type | What it actually requires |
|---|---|
| Bug | Find the layer where the wrong value originates. Fix there only. |
| New feature | Identify the smallest additive change. No opportunistic refactoring. |
| UI tweak | Template and CSS only. If you need a view change, the feature scope is wrong. |
| New API endpoint | Design the resource first. Code second. |
| Performance problem | Diagnose the query. Do not cache or denormalize before profiling. |
| React migration step | Add a new API resource. Touch nothing else. |

**Step 2 — Identify the owning layer**

Ask: where does this logic naturally live?

- A constraint on data shape or relationship → model `clean()`
- A reusable operation across multiple entry points → service function
- Request parsing, permission enforcement, response shaping → view
- Conditional rendering, formatting → template

If the answer is ambiguous, the logic belongs one layer closer to the data than your instinct suggests.

**Step 3 — Check if it already exists**

Search for the function before writing it. If something similar exists:
- Can you extend it without changing its signature?
- Can you call it with different arguments?
- If you must change its return shape, identify every caller first.

**Step 4 — Define the minimal change**

State explicitly what files will change and why. If more than three files are changing for a one-sentence feature request, you are doing too much.
If the solution requires touching unrelated files, reconsider the approach.
Unrelated changes are a signal of overreach.

---

## 3. Pattern Recognition

This codebase is pattern-consistent. Every common operation has an established implementation. Locate it and match it — do not invent a parallel approach.

**Before writing, ask: where is the nearest existing example of this exact operation?**

| Operation | Where to look |
|---|---|
| Portal stat card | Any existing stat card block in the target template |
| Portal chart | Existing ECharts block in the same template; match builder function, `setOption(opt, true)`, resize observer |
| Control panel CRUD page | Nearest existing CRUD group (accounts, products, tokens) |
| Control panel form | Nearest existing form class in `control/forms.py` |
| Service function | Adjacent functions in the same `services.py` |
| API endpoint | `ActiveContractView` in `api/views.py` — match exactly |
| Audit log call | `_log()` usage in any existing control view |
| Permission decorator | `@perm_required` usage in any existing control view |
| PRG redirect | `request.session` stash pattern in any create/edit view |

If no existing pattern covers the operation, you are in uncharted territory. Slow down. Design before implementing. Ask if needed.

---

## 4. Decision Heuristics

### Layer placement

| Situation | Correct placement | Wrong placement |
|---|---|---|
| "Does this data satisfy a constraint?" | Model `clean()` | View-level validation |
| "Do two views need the same computation?" | Service function | Duplicated in both views |
| "Does this require the HTTP request?" | View | Service |
| "Is this about what to show, not what to compute?" | Template | View |
| "Does this aggregate across multiple models?" | Service | Template |
| "Does this enforce a business rule on every write?" | Model | Service or view |

### When to extract a service

Two identical or near-identical implementations in two views → extract to a service immediately, before a third appears. One copy is acceptable. Two is the extraction trigger.

Do not extract preemptively. Do not create a service function that has exactly one caller and no meaningful isolation benefit.

### When to add a migration

Any model field addition, removal, rename, or constraint change requires a migration. There are no exceptions. Never hand-edit an applied migration.

### When to add a new URL

Only when the operation represents a genuinely distinct resource or action. Do not add a new URL to avoid a query parameter. Filters, pagination, and scoping always go in query params.

### When to touch shared infrastructure

`portal.css`, `base.html`, `portal.js`, service functions with multiple callers — these are shared. A change to any of them is never local. Before editing, enumerate every consumer.

---

## 5. Smell Detection

Stop and reassess immediately when you encounter any of these:

**Logic in the wrong layer**
- A template computing a derived value instead of receiving it from the view context.
- A view containing business logic that could be called from a second view or API.
- A service function receiving `request` or importing from `django.http`.
- A model method making decisions that depend on the HTTP context.

**Duplication**
- A new function that does what an existing function does with a slightly different name.
- The same ORM query written twice in two views.
- A context variable built in a view that replicates what a service already returns.
- A new abstraction introduced before duplication exists (premature generalization)

**Structural drift**
- A new endpoint that returns multiple unrelated data types in one response.
- A URL segment encoding filter state that belongs in a query parameter.
- Frontend code computing a value that the backend already annotates.
- A hardcoded string literal where a model constant (`STATUS_ACTIVE`, `STATUS_ACCEPTED`) exists.

**Silent failure**
- A bare `except Exception` block that returns empty data without logging.
- A `get_or_none` pattern that silently hides a missing object.
- A template that renders nothing when the context variable is missing, with no error surfaced.

**Scope creep**
- Changing a working function's signature because the new feature would be easier if it returned something slightly different.
- Cleaning up adjacent code while fixing an unrelated bug.
- Adding a migration for a field that the task does not require.

---

## 6. Execution Style

**Read before writing.** Always read the full context of what you are about to change. At minimum: the target function, its callers, and the template that consumes the output.

**Read all callers before modifying shared logic.**
If a function, service, or context variable is used in multiple places, read every caller before changing it. Never assume usage — verify it.

**One logical change per task.** A bug fix does not include a refactor. A new feature does not include cleanup of adjacent code. Conflating changes makes review impossible and introduces regression risk.

**Match the file's existing style exactly.** If the file uses a particular naming convention, comment style, or structural pattern — replicate it. Do not introduce a competing style in the same file.

**Write no comments by default.** Only comment when the reason is genuinely non-obvious and cannot be inferred from the code. A comment explaining what the code does is noise. A comment explaining why a non-obvious constraint exists is signal.

**Do not add defensive code for impossible scenarios.** At the view layer, trust that the service has validated. At the template layer, trust that the view has prepared the context. Only validate at true system boundaries: user input, external API calls.

**Never rename a public symbol without instruction.** URL names, model fields, API JSON keys, `db_table` values — renaming these has invisible callers. Do not do it unless explicitly asked, and never without identifying all impact points first.

---

## 7. Debugging Strategy

**Follow the data, not the symptom.** A wrong value in the template has an origin. Trace backwards: template → view context → service return → ORM query → model.

**Step 1: Locate where the wrong value first appears.**
Work backwards from what is rendered. Do not patch at the template level if the error is in the query.

**Step 2: Verify the query.**
Most data bugs are query bugs — missing filter, wrong annotation, absent `select_related`, incorrect aggregation. Examine the generated SQL before touching view logic.

**Step 3: Verify the service contract.**
Does the service return the shape the view expects? Has the return shape drifted after a recent change? Check all callers, not just the one exhibiting the bug.

**Step 4: Isolate before fixing.**
Reproduce the bug with the smallest possible input. A fix applied to a misunderstood bug creates a second bug.

**Step 5: Fix at the source layer.**
If the value is wrong in the template, the fix is not in the template. Trace it to where the value is produced incorrectly and fix it there.

**Step 6: Verify adjacency.**
After the fix, identify all other views, templates, or services that share the changed component. Verify they still behave correctly.

**Common misdiagnoses to avoid**

| Symptom | Wrong diagnosis | Correct starting point |
|---|---|---|
| Chart renders empty | Template bug | Verify the context variable the chart reads from |
| Form validation fails unexpectedly | Form bug | Check model `clean()` — constraint may be there |
| API returns wrong data | View bug | Check the service return, then the query |
| Page redirect goes to wrong URL | View bug | Check the URL name resolution and `reverse()` arguments |
| Permission denied unexpectedly | Decorator bug | Check the user's actual group and permission assignment |

---

## 8. API Thinking

Every endpoint must answer one question before any code is written:

**"What resource is this, and what operation am I performing on it?"**

If that question cannot be answered in one sentence, the endpoint design is wrong.

If the frontend needs "everything for a page", you are designing the API wrong.
Break it into resources.

**Resource identification**

A resource is a domain object — a contract, a sale, a token, a pharmacy account. An endpoint represents a resource, not a screen and not a use case.

- Correct: `/api/v1/contracts/{id}/sales/?month=2026-04` — the sales of a specific contract, filtered by month.
- Wrong: `/api/v1/dashboard-summary/` — a screen blob, not a resource.

**Filter and scope via query parameters**

If the same resource is needed with different filters, use query parameters — not new endpoints. A new endpoint is only justified when the resource type genuinely differs.

**Aggregations are sub-resources**

Stats and computed summaries sit under the parent resource they derive from. They are not injected as extra fields on the parent response.

**Error handling**

Always use the existing `_error()` helper and existing error codes. Do not invent new envelope shapes or new error code strings. Consistency of error format matters to API consumers.

**View responsibility boundary**

An API view does exactly three things: parse the request, call a service, format the response. Business logic does not live in the view. The view is a translation layer, not a computation layer.

**Authentication**

New endpoints inherit `APITokenAuthentication` automatically. Do not add per-view authentication overrides unless there is an explicit, documented reason.

---

## 9. Safe Extension Mindset

Extending this system safely means adding without displacing. Every change has a blast radius. Your job is to minimize it.

**Default to additive.**
New fields, new views, new service functions, new template blocks — these are low risk. Modifying existing shared components is high risk. When both can achieve the goal, choose additive.

**Enumerate consumers before touching shared components.**
Before editing a service function, a CSS class in `portal.css`, a base template, or a context variable name — list every place it is consumed. There are no truly local changes to shared infrastructure.

**Preserve return shape when extending services.**
If a service function is extended to support a new caller, its existing return shape must remain intact for existing callers. Add to the return, do not reshape it.

**Do not alter a working flow to make a new flow easier.**
Build the new flow around the existing one. Modifying a stable flow to accommodate a new requirement is how regressions enter the system.

**Chart and JS isolation.**
When adding a new chart to a template, do not alter the initialization order or shared state of existing charts. Charts may share resize observers or filter state. New chart code must be self-contained.

**Portal and control panel are separate surfaces.**
Work in one or the other per task. Do not make cross-panel changes unless the task explicitly requires it. Changes to shared CSS or base templates affect both and require verifying both.

**React branch discipline.**
All backend work goes to `develop`. The `feature/react-ui` branch receives only React-specific scaffolding and API additions. Never merge `feature/react-ui` without explicit instruction. Never restructure the Django app layout for React convenience.

---

## 10. When to Push Back

Push back clearly and immediately — do not silently comply with a request that violates system principles.

**Push back when the request would:**

- Violate a rule in CLAUDE.md. State the rule. Propose a compliant alternative. Do not proceed until the conflict is resolved.
- Duplicate logic that already exists. Point to the existing implementation. Propose reuse or extraction.
- Produce a screen-shaped API instead of a resource-shaped one. Redesign the endpoint before implementing.
- Require changes to a locked schema (`Sale`, `SaleImport`, `Contract`, `Contract_Product`) without an explicit migration plan from the user.
- Modify a locked file (`settings.py`, applied migrations, auth flow, token hashing) without the user acknowledging the lock.
- Bundle a refactor into a feature task. Separate the concerns and confirm which to do first.
- Collapse React migration phases. Phases exist to isolate risk. Do not skip from Phase 1 to Phase 3.
- Add frontend computation that belongs server-side. The backend annotates; the frontend renders.

**How to push back:**

1. Name the specific conflict precisely.
2. Propose a compliant alternative that achieves the user's goal.
3. Wait for a decision before proceeding.

Do not push back on implementation style preferences. Do not push back on things that are discretionary. Reserve pushback for genuine principle violations — and when you use it, be specific.

Silently implementing a bad request is worse than refusing it.

---
**End of SKILL.md.**
CLAUDE.md governs rules. ARCHITECTURE.md governs structure. This file governs execution.
When in doubt about a rule, CLAUDE.md wins. When in doubt about a pattern, read the nearest existing implementation.
