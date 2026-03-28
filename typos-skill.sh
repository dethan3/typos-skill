#!/bin/bash
# Typos Spell Check Skill with LLM Confirmation
# Usage: typos-skill.sh [options] [path...]

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SELF_CMD=$(printf '%q' "$SCRIPT_DIR/typos-skill.sh")

usage() {
    cat <<'EOF'
Usage: typos-skill.sh [options] [path...]

Options:
  --diff                 Show proposed changes after the LLM review output
  --export-review <file> Write a review JSONL file for LLM confirmation
  --apply-review <file>  Apply only approved corrections from a review file
  --apply-all            Apply all typos suggestions without review
  -h, --help             Show this help message

Notes:
  - Default path is current directory.
  - Review output is intended for LLM confirmation before applying changes.
  - --diff, --apply-review, and --apply-all are mutually exclusive.
  - --export-review is only available in default review mode.
EOF
}

ACTION="review"
ACTION_EXPLICIT=0
PATHS=()
EXPORT_REVIEW_FILE=""
REVIEW_FILE=""
PYTHON_BIN=""

set_action() {
    local requested="$1"
    if [[ "$ACTION_EXPLICIT" -eq 1 && "$ACTION" != "$requested" ]]; then
        echo "Error: --diff, --apply-review, and --apply-all are mutually exclusive." >&2
        exit 2
    fi
    ACTION="$requested"
    ACTION_EXPLICIT=1
}

require_python() {
    if [[ -n "$PYTHON_BIN" ]]; then
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
        return 0
    fi

    echo "Error: python3 is required to parse typos output." >&2
    echo "Install python3 or ensure it is on PATH." >&2
    exit 127
}

format_paths() {
    local out=()
    local path
    for path in "$@"; do
        out+=("$(printf '%q' "$path")")
    done
    if [[ ${#out[@]} -gt 0 ]]; then
        printf '%s' "${out[*]}"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --diff)
            set_action "diff"
            shift
            ;;
        --apply-review)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for --apply-review" >&2
                usage >&2
                exit 2
            fi
            set_action "apply-review"
            REVIEW_FILE="$2"
            shift 2
            ;;
        --export-review)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for --export-review" >&2
                usage >&2
                exit 2
            fi
            EXPORT_REVIEW_FILE="$2"
            shift 2
            ;;
        --apply-all)
            set_action "apply-all"
            shift
            ;;
        --apply)
            echo "Use --apply-review <file> to apply approved fixes or --apply-all to apply everything." >&2
            exit 2
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            PATHS+=("$1")
            shift
            ;;
    esac
done

if [[ $# -gt 0 ]]; then
    PATHS+=("$@")
fi

if [[ -n "$EXPORT_REVIEW_FILE" && "$ACTION" != "review" ]]; then
    echo "Error: --export-review can only be used in review mode." >&2
    exit 2
fi

if [[ "$ACTION" == "apply-review" ]]; then
    if [[ -z "$REVIEW_FILE" ]]; then
        echo "Error: --apply-review requires a review file." >&2
        exit 2
    fi
    if [[ ! -f "$REVIEW_FILE" ]]; then
        echo "Error: review file not found: $REVIEW_FILE" >&2
        exit 2
    fi
    require_python
    "$PYTHON_BIN" "$SCRIPT_DIR/scripts/apply-review.py" "$REVIEW_FILE"
    exit 0
fi

if [[ ${#PATHS[@]} -eq 0 ]]; then
    PATHS=(.)
fi

echo "🔍 Running typos spell check on: ${PATHS[*]}"
echo "======================================"

require_python

if ! command -v typos >/dev/null 2>&1; then
    echo "Error: typos CLI not found. Install with: cargo install typos-cli" >&2
    exit 127
fi

if [[ "$ACTION" == "diff" ]]; then
    echo ""
    echo "Showing diff of proposed changes:"
    typos --diff "${PATHS[@]}"
    exit $?
fi

if [[ "$ACTION" == "apply-all" ]]; then
    echo ""
    echo "Applying all typos corrections (no LLM filtering)..."
    typos --write-changes "${PATHS[@]}"
    exit $?
fi

TMP_BASE_DIR="${TMPDIR:-/tmp}"
TYPOS_OUTPUT_FILE=$(mktemp "${TMP_BASE_DIR}/typos-skill-output.XXXXXX")
TYPOS_ERROR_FILE=$(mktemp "${TMP_BASE_DIR}/typos-skill-error.XXXXXX")
cleanup() {
    rm -f "$TYPOS_OUTPUT_FILE" "$TYPOS_ERROR_FILE"
}
trap cleanup EXIT

set +e
typos --format json "${PATHS[@]}" >"$TYPOS_OUTPUT_FILE" 2>"$TYPOS_ERROR_FILE"
TYPOS_STATUS=$?
set -e

if [[ ! -s "$TYPOS_OUTPUT_FILE" ]]; then
    if [[ $TYPOS_STATUS -ne 0 ]]; then
        echo "Error: typos failed (exit $TYPOS_STATUS)." >&2
        if [[ -s "$TYPOS_ERROR_FILE" ]]; then
            sed 's/^/  /' "$TYPOS_ERROR_FILE" >&2
        fi
        exit "$TYPOS_STATUS"
    fi
    echo "✅ No spelling errors found!"
    exit 0
fi

if [[ -s "$TYPOS_ERROR_FILE" ]]; then
    echo "typos warnings:" >&2
    sed 's/^/  /' "$TYPOS_ERROR_FILE" >&2
    echo "" >&2
fi

# Parse typos and create review export with conservative triage
echo ""
echo "📝 Found spelling errors. Preparing for LLM review..."
echo ""

PATHS_DISPLAY=$(format_paths "${PATHS[@]}")

if [[ -n "$EXPORT_REVIEW_FILE" ]]; then
    "$PYTHON_BIN" "$SCRIPT_DIR/scripts/export-review.py" \
        "$TYPOS_OUTPUT_FILE" \
        "$EXPORT_REVIEW_FILE"
else
    "$PYTHON_BIN" "$SCRIPT_DIR/scripts/export-review.py" \
        "$TYPOS_OUTPUT_FILE"
fi

echo "======================================"
echo ""
echo "📋 Instructions for LLM Review:"
echo ""
echo "The review export already applies conservative built-in triage."
echo "For each item:"
echo "1. Read the file at the specified line to confirm the context"
echo "2. Use bucket / suggested_status / preferred_action / reason as the default decision"
echo "3. Override only when the source context clearly justifies it"
echo ""
echo "Preferred flow:"
echo "1. Run with --export-review to create a review file"
echo "2. Update each JSON line with:"
echo "   - status: ACCEPT CORRECT | FALSE POSITIVE | CUSTOM"
echo "   - correction: required when status is CUSTOM"
echo "   - reason: keep or refine the explanation for why the item is safe to change or should be skipped"
echo '   - prefer `.typos.toml` suggestions for repeated false positives before editing source'
echo "   - keep byte_offset / occurrence_index unchanged for accurate apply"
echo "3. Apply with --apply-review <file>"
echo ""
echo "Next steps:"
if [[ -n "$EXPORT_REVIEW_FILE" ]]; then
    echo "  - Apply approved: $SELF_CMD --apply-review $(printf '%q' "$EXPORT_REVIEW_FILE")"
else
    echo "  - Export review: $SELF_CMD --export-review review.jsonl ${PATHS_DISPLAY}"
fi
echo "  - Preview all:   $SELF_CMD --diff ${PATHS_DISPLAY}"
echo "  - Apply all:     $SELF_CMD --apply-all ${PATHS_DISPLAY}"
