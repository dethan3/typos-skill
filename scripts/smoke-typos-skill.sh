#!/bin/bash
# Smoke test for typos-skill.sh

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/smoke-typos-skill.sh

Runs a minimal smoke test for typos-skill.sh. This checks the help output
and, when typos is installed, verifies review export metadata on a temporary
sample plus runs a read-only scan on the repo root.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SKILL="$ROOT_DIR/typos-skill.sh"

if [[ ! -x "$SKILL" ]]; then
    echo "Error: typos-skill.sh is not executable. Run: chmod +x typos-skill.sh" >&2
    exit 1
fi

"$SKILL" --help >/dev/null

if ! command -v typos >/dev/null 2>&1; then
    echo "SKIP: typos CLI not found; install with: cargo install typos-cli" >&2
    exit 0
fi

TMP_DIR=$(mktemp -d)
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

cat > "$TMP_DIR/sample.txt" <<'EOF'
thsi pn pn
EOF

"$SKILL" --export-review "$TMP_DIR/review.jsonl" "$TMP_DIR/sample.txt" >/dev/null

python3 - "$TMP_DIR/review.jsonl" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    items = [json.loads(line) for line in handle if line.strip()]

assert items, "expected exported review items"
for item in items:
    for key in ("reason", "bucket", "suggested_status", "preferred_action"):
        assert item.get(key), f"missing {key}"

assert any(item.get("preferred_action") == "UPDATE_TYPOS_TOML" for item in items), (
    "expected at least one .typos.toml suggestion"
)
PY

"$SKILL" "$ROOT_DIR" >/dev/null

echo "OK: typos-skill smoke test passed."
