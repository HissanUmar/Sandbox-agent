# Issue Register — V2 Assessment Response

Status per issue: confirmed (real), plausible (needs verification),
disputed (I disagree with scope/severity), documentation (README wording).

## Batch 1 — environment execution correctness

- [X] **Issue 1 — prompt ignored** — `confirmed` (needs verification first:
      does hospital actually use prompt.md, or is qwen3 ignoring SYSTEM?)
      Severity: Critical. File: `agent.py`.
      Test: run hospital with a prompt that says "always answer in French"
      and see if the answer is French. If not, SYSTEM is being used.

- [X] **Issue 2 — 404/409 collapse** — `confirmed` (documented limitation;
      the assessment is right that the YAML *declares* both and the handler
      can't pick). Severity: High. File: `pipeline/sandbox.py`.
      Fix: add `precheck:` query or `RETURNING`-based disambiguation.
      Test: cancel a shipped order → 409, cancel a missing order → 404.

- [X] **Issue 3 — hospital availability not enforced on write** — `confirmed`.
      Severity: High. File: `environments/hospital/sandbox.yaml`.
      Test: two POSTs for the same doctor/time; second must fail.

- [X] **Issue 4 — tool/API optionality mismatch** — `confirmed` (I wrote
      `available_at: str = None` in the tool, `required: true` in the YAML;
      that's inconsistent). Severity: Medium. File:
      `environments/hospital/tools.py`.
      Fix: make the tool param required (no default), matching the API.

- [X] **Issue 5 — response params not substituted** — `confirmed` (documented
      limitation, but the YAML promises the substitution).
      Severity: Medium. File: `pipeline/sandbox.py` `_resolve_body`.
      Test: cancel missing order → message contains the id, not `{id}`.

## Batch 2 — grading trustworthiness

- [X] **Issue 7 — grader checks presence, not exactness** — `confirmed`.
      Severity: High. File: `grade.py`.
      Fix: add `exactly: true` mode to task YAML; when set, compare row
      count and full row set, not "at least one."
      Test: task expects 1 appointment; agent creates 2; grader must fail.

## Batch 3 — portability, lifecycle, coverage

- [~] **Issue 6 — module-level and process-level state** — `confirmed`.
      Severity: Medium (it's V3 work, but the assessment is right that the
      README shouldn't imply concurrency is safe). Files:
      `pipeline/sandbox.py`, `environments/*/_runtime.py`.
      Add: restore `os.environ` in `finally` (3-line fix, do it now).
      Defer: per-run runtime object (V3).

- [ ] **Issue 8 — hardcoded env list** — `plausible` (true, but V5 scope per
      roadmap; not a V2 blocker). Severity: Medium as a claim, Low as an
      action. File: `run_agent.py`.
      Defer unless you want to add a third environment soon.

- [ ] **Issue 9 — limited schema constraints** — `confirmed` (no NOT NULL,
      UNIQUE, CHECK, defaults). Severity: Medium. Files: `sandbox.py`,
      `validate.py`.
      Fix: add them one at a time, with validation and a test per constraint.
      Don't do this speculatively.

- [ ] **Issue 10 — no hospital integration tests** — `confirmed`.
      Severity: High. File: `test_sandbox.py` (needs to test both).
      Fix: parametrize the six tests over `[shop, hospital]` where the
      assertions make sense; add hospital-specific ones for FK seed order
      and availability enforcement.

- [~] **Issue 11 — unbounded startup, unjoined threads** — `confirmed`
      (the startup loop has no timeout; teardown doesn't `join` threads).
      Severity: Medium. File: `pipeline/sandbox.py`.
      Fix: startup timeout with clear error; `thread.join(timeout=2)` in
      teardown. Test: kill uvicorn mid-start, sandbox fails fast.

- [ ] **Issue 12 — shallow SQL config validation** — `confirmed` (the `?`
      count is naive; table/column existence isn't checked).
      Severity: Medium. Files: `validate.py`.
      Fix: SQL-aware placeholder count (skip inside string literals and
      comments); table/column existence check from the schema.
      Defer the full SQL smoke test unless you add more endpoints.

## Disputed or documentation-only

- [ ] **Issue 13 — "not fully code-free"** — `documentation`. The README
      doesn't claim code-free; the roadmap explicitly says tool generation
      is not a requirement. Action: tighten README wording so a reader
      can't infer "YAML-only" from the architecture description.
      No code change.

- [ ] **Issue 8 severity** — `disputed`. Adding an environment requires
      editing `choices` in `run_agent.py`. That's true, but the roadmap's
      V2 criteria don't include "no runner edits." The assessment treats it
      as a V2 gap; I'd call it V5 work.

- [ ] **"V2 not complete" overall verdict** — `disputed` in scope, agreed in
      substance. The README's "V2 complete" should be read as "the V2
      *roadmap* (environment split + second domain + state grading) is
      demonstrated." The assessment's stronger claim ("not a generic
      framework") is also true, but it's a statement about V5 scope, not
      V2. Action: rewrite the README's V2 section to state precisely what
      was proven and what wasn't.

## Not in the assessment, worth adding

- [ ] **`os.environ` never restored after `sb.run()`** — `confirmed`
      (silent; makes stale URLs visible to anything that reads `SB_API_*`
      between runs). File: `pipeline/sandbox.py`.
      Fix: `saved = dict(os.environ)` before `update`; restore in `finally`.
      ~4 lines.
      Test: after `sb.run()`, `"SB_API_ORDERS" not in os.environ`.

- [ ] **Does the hospital run actually use prompt.md?** — this is the
      verification step for Issue 1, not a separate issue. Run the hospital
      task with a prompt that forces a distinctive output format. If the
      output doesn't change, Issue 1 is confirmed and the hospital "pass"
      was the model following tool docstrings, not the environment config.