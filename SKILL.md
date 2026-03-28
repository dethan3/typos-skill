---
name: typos
description: Run typos CLI on files and produce LLM-reviewable spelling fixes with optional diff/apply.
---

# Typos Spell Check with LLM Review

Use this skill when the user wants to scan files for spelling errors with the
`typos` CLI and confirm corrections via LLM before applying changes. The export
step applies conservative built-in triage first so the reviewer does not need
to improvise basic false-positive rules.

## Workflow

1. Resolve the absolute path to `typos-skill.sh` in the installed skill
   directory, then run `<skill-dir>/typos-skill.sh --export-review review.jsonl
   [path...]` to generate a review file plus a human-readable summary.
2. Read file context at the reported path and line; use the exported
   `bucket`, `suggested_status`, `preferred_action`, and `reason` as the
   default review stance.
3. Update each JSON line:
   - `status`: `ACCEPT CORRECT`, `FALSE POSITIVE`, or `CUSTOM`
   - `correction`: required when status is `CUSTOM`
   - `reason`: keep or refine the explanation for why the item should or
     should not be changed
4. Prefer `.typos.toml` suggestions for repeated false positives before
   editing source one by one.
5. Apply approved changes with `<skill-dir>/typos-skill.sh --apply-review
   review.jsonl`.
6. Optional: use `--diff` to preview or `--apply-all` to skip review.

## Review File Rules

- `status` is case-insensitive and supports `_` / `-` separators.
- Accepted statuses:
  - apply: `ACCEPT`, `ACCEPT CORRECT`, `CUSTOM`
  - skip: `FALSE POSITIVE`, `FALSE POSITIVE?`, `FALSEPOSITIVE`, `SKIP`, `REJECT`
- `CUSTOM` requires non-empty `correction`.
- Exported advisory fields:
  - `bucket`: conservative triage bucket
  - `suggested_status`: default review decision
  - `preferred_action`: `REVIEW_SOURCE`, `KEEP_SOURCE`, or `UPDATE_TYPOS_TOML`
  - `reason`: why the item is safe to change or should be skipped
  - `toml_section` / `toml_snippet`: suggested `.typos.toml` update when safer
    than editing source
- Do not edit locator fields unless you know what you are doing:
  - keep `byte_offset` unchanged
  - keep `occurrence_index` unchanged
  - keep `line_num` consistent with source
- If `byte_offset` is removed and the same typo appears multiple times on one
  line, `occurrence_index` is required to disambiguate the target occurrence.

## Execution Context

- Do not assume the current working directory is the skill directory.
- Invoke `typos-skill.sh` via its absolute path from the installed skill
  directory.
- For user-installed Codex skills, that path is typically
  `${CODEX_HOME:-$HOME/.codex}/skills/typos/typos-skill.sh`.
- The tool no longer requires running from repo root for `--apply-review`.
- Relative `path` values in `review.jsonl` are resolved relative to the review
  file directory.

## Failure Scenarios and Conflict Handling

- `byte_offset mismatch`: source file changed after export.
- `multiple occurrences on the same line`: ambiguous target without
  `byte_offset` / `occurrence_index`.
- `overlapping replacements detected`: two approved edits collide.
- `Missing file`: review `path` is invalid for current workspace.

When any conflict above occurs, apply step fails fast and writes nothing. Fix by
re-exporting review (`--export-review`) from the latest files and re-approving.

## Dependencies

- `typos` (`cargo install typos-cli`)
- `python3`

## Notes

- Script: `typos-skill.sh`
- Export helper: `scripts/export-review.py`
- Apply helper: `scripts/apply-review.py`
- Smoke test: `scripts/smoke-typos-skill.sh`
