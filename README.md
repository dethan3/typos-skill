# Typos Skill for Claude Code and Codex

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blue)](https://clawhub.com)

Use the `typos` CLI to find spelling issues, export them into a review file,
let an agent or LLM confirm each change, and apply only the approved fixes.

## Who This Is For

This repository is primarily packaged as a Skill for:

- Claude Code
- Codex

It wraps `typos` in a safer review workflow:

1. scan files for spelling issues
2. export a `review.jsonl` file
3. review each item with an agent or manually
4. apply only approved corrections

If you only want raw spell checking, you can run `typos` directly. This Skill is
useful when you want an agent-assisted review step before files are modified.

## Quick Start

### Prerequisites

Install the required tools:

```bash
cargo install typos-cli
python3 --version
```

### Install in Claude Code

Copy this repository into your Claude skills directory:

```bash
mkdir -p ~/.claude/skills
cp -r /path/to/typos-skill ~/.claude/skills/typos
chmod +x ~/.claude/skills/typos/typos-skill.sh
chmod +x ~/.claude/skills/typos/scripts/smoke-typos-skill.sh
```

Start a new Claude Code session in the target repository, then invoke the skill
explicitly:

```text
Use the typos skill to scan this repo, export review.jsonl, and apply only approved fixes.
```

### Install in Codex

Recommended method, from a Codex session:

```text
Use $skill-installer to install the skill from https://github.com/luojiyin1987/typos-skill with path . and name typos.
```

If your environment does not expose `$skill-installer`, install manually:

```bash
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$SKILLS_DIR"
cp -r /path/to/typos-skill "$SKILLS_DIR/typos"
chmod +x "$SKILLS_DIR/typos/typos-skill.sh"
chmod +x "$SKILLS_DIR/typos/scripts/smoke-typos-skill.sh"
```

After installation, start a new Codex session in the target repository and use:

```text
Use $typos to scan this repo, export review.jsonl, then apply approved corrections.
```

## How It Works

The core workflow is always the same:

1. Export suggestions:

   ```bash
   ./typos-skill.sh --export-review review.jsonl [path...]
   ```

2. Review each JSON line in `review.jsonl`:
   - mark accepted items as `ACCEPT` or `ACCEPT CORRECT`
   - mark false positives as `FALSE POSITIVE`
   - use `CUSTOM` and set `correction` when you want your own replacement

3. Apply approved changes:

   ```bash
   ./typos-skill.sh --apply-review review.jsonl
   ```

This repository does not automatically call an LLM. The Skill produces a
reviewable file so Claude Code, Codex, or a human can make the final decision
before edits are applied.

## Agent Usage

### Claude Code Prompts

```text
Use the typos skill to scan this repository and summarize the spelling issues before changing anything.
```

```text
Use the typos skill to run --export-review review.jsonl on docs/ and README.md, mark each finding as ACCEPT / FALSE POSITIVE / CUSTOM, then apply only approved fixes.
```

### Codex Prompts

```text
Use $typos to scan this repository and summarize the spelling issues before changing anything.
```

```text
Use $typos to run --export-review review.jsonl on src/ and docs/, review each finding, then apply only ACCEPT and CUSTOM fixes.
```

```text
Use $typos to check README.md and docs/, mark false positives, and show me the diff before applying changes.
```

```text
Use $typos to run --apply-all on docs/ only. Avoid touching code files.
```

## CLI Reference

### Basic Usage

```bash
# Check current directory
./typos-skill.sh

# Check specific files or directories
./typos-skill.sh src/ tests/ README.md

# Export review for agent/LLM processing
./typos-skill.sh --export-review review.jsonl src/
```

### Commands

```bash
# Preview all proposed changes without applying them
./typos-skill.sh --diff [path...]

# Apply only approved changes from a review file
./typos-skill.sh --apply-review review.jsonl

# Apply all suggestions without review
./typos-skill.sh --apply-all [path...]
```

## Review File Format

The review file (`review.jsonl`) contains one JSON object per line:

```json
{
  "path": "relative/path/to/file",
  "line_num": 42,
  "byte_offset": 123,
  "occurrence_index": 1,
  "typo": "<detected-typo>",
  "corrections": ["<suggested-correction>"],
  "status": "PENDING",
  "correction": ""
}
```

### Status Values

| Status | Meaning |
| --- | --- |
| `PENDING` | Initial exported state. Review required before apply. |
| `ACCEPT` | Apply the suggested correction. |
| `ACCEPT CORRECT` | Apply the suggested correction. |
| `FALSE POSITIVE` | Skip this item. |
| `FALSE POSITIVE?` | Skip this item. |
| `SKIP` | Skip this item. |
| `REJECT` | Skip this item. |
| `CUSTOM` | Apply the value in `correction`. |

Important rules:

- `PENDING` cannot be applied directly. Change each item to a final review
  status before running `--apply-review`.
- Do not modify `byte_offset`, `occurrence_index`, or `line_num` unless you
  understand how locator matching works.
- `CUSTOM` requires a non-empty `correction`.
- If files changed after export, re-run `--export-review` before applying.

## Configuration

Create a `.typos.toml` file in your project root to customize spell checking:

```toml
[files]
extend-exclude = [
  "*.min.js",
  "vendor/*",
  "node_modules/*"
]
```

You can also add project-specific words:

```toml
[default.extend-words]
npm = "npm"
github = "github"
api = "api"
cli = "cli"
```

## Development

### Project Structure

```text
typos-skill/
├── SKILL.md                     # Skill instructions for the agent
├── skill.json                   # Skill metadata
├── typos-skill.sh               # Main entry point
├── scripts/
│   ├── apply-review.py          # Applies approved fixes from review.jsonl
│   └── smoke-typos-skill.sh     # Minimal smoke test
├── agents/
│   └── openai.yaml              # Agent UI metadata
└── .typos.toml                  # Default repository typos configuration
```

### Smoke Test

```bash
./scripts/smoke-typos-skill.sh
```

## Compatibility Note

This repository is written as a portable agent skill workflow. The README is
optimized for Claude Code and Codex because those are the primary usage paths
documented here.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
