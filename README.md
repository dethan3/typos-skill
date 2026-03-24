# Typos Skill - AI-Powered Spell Check with LLM Review

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blue)](https://clawhub.com)

A powerful spell-checking skill for OpenClaw that uses the `typos` CLI tool to detect spelling errors and provides LLM-assisted review before applying corrections.

## ✨ Features

- 🔍 **Automatic spell checking** using the `typos` CLI tool
- 🤖 **LLM-powered review** for intelligent correction approval
- 📝 **Interactive workflow** with human-in-the-loop validation
- 🔄 **Safe application** with preview and rollback options
- 📁 **Batch processing** for multiple files and directories
- ⚙️ **Customizable rules** via `.typos.toml` configuration

## 🚀 Quick Start

### Prerequisites

1. Install `typos` CLI:

   ```bash
   cargo install typos-cli
   # or using package manager (if available)
   # brew install typos-cli (macOS)
   # Debian/Ubuntu: use `cargo install typos-cli`
   ```

2. Install Python 3.8+ (required for review processing)

### Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/luojiyin1987/typos-skill.git
   cd typos-skill
   ```

2. Make the script executable:

   ```bash
   chmod +x typos-skill.sh
   ```

## 📖 Usage

### Basic Spell Check with LLM Review

```bash
# Check current directory
./typos-skill.sh

# Check specific files or directories
./typos-skill.sh src/ tests/ README.md

# Export review for LLM processing
./typos-skill.sh --export-review review.jsonl src/
```

### Review and Apply Corrections

1. **Export review file**:

   ```bash
   ./typos-skill.sh --export-review review.jsonl [path...]
   ```

2. **Review with LLM**:
   - Open `review.jsonl` and examine each suggested correction
   - Update `status` field:
     - `ACCEPT` or `ACCEPT CORRECT` - Apply the suggested correction
     - `FALSE POSITIVE` - Skip this suggestion
     - `CUSTOM` - Provide custom correction in `correction` field
   - Do not modify `byte_offset`, `occurrence_index`, or `line_num` unless you know what you're doing

3. **Apply approved changes**:

   ```bash
   ./typos-skill.sh --apply-review review.jsonl
   ```

### Advanced Options

```bash
# Preview changes without applying
./typos-skill.sh --diff

# Apply all suggestions without review (use with caution!)
./typos-skill.sh --apply-all

# Check selected paths explicitly
./typos-skill.sh --export-review review.jsonl docs/ README.md
```

## 📋 Review File Format

The review file (`review.jsonl`) contains one JSON object per line with the following structure:

```json
{
  "path": "relative/path/to/file",
  "line_num": 42,
  "byte_offset": 123,
  "occurrence_index": 1,
  "typo": "recieve",
  "corrections": ["receive"],
  "status": "PENDING",
  "correction": ""
}
```

### Status Values

| Status                       | Description                          | Action                    |
| ---------------------------- | ------------------------------------ | ------------------------- |
| `PENDING`                    | Initial exported state before review | ⏳ Review required        |
| `ACCEPT` or `ACCEPT CORRECT` | Apply the suggested correction       | ✅ Apply                  |
| `FALSE POSITIVE`             | Mark as false positive               | ❌ Skip                   |
| `FALSE POSITIVE?`            | Uncertain false positive             | ⚠️ Skip with note         |
| `SKIP` or `REJECT`           | Skip this correction                 | ❌ Skip                   |
| `CUSTOM`                     | Apply custom correction              | ✏️ Use `correction` field |

## ⚙️ Configuration

### `.typos.toml` Configuration

Create a `.typos.toml` file in your project root to customize spell checking:

```toml
[files]
extend-exclude = [
  "*.min.js",
  "vendor/*",
  "node_modules/*"
]
```

### Common Typos Rules

You can add custom dictionaries or ignore patterns:

```toml
[default.extend-words]
npm = "npm"
github = "github"
api = "api"
cli = "cli"
```

## 🔧 Integration with Claude Code and Codex

### Install in Claude Code

1. Copy this repository to your Claude skills directory:

   ```bash
   mkdir -p ~/.claude/skills
   cp -r /path/to/typos-skill ~/.claude/skills/typos
   ```

2. Start a new Claude Code session in your target project.

3. Ask Claude to use this skill explicitly, for example:

   ```text
   Use the typos skill to scan this repo, export review.jsonl, and apply only approved fixes.
   ```

### Install in Codex

Choose one of the installation methods below.

#### Recommended Method

From a Codex session, ask the built-in `$skill-installer` system skill to
install this repository as `typos`:

```text
Use $skill-installer to install the skill from https://github.com/luojiyin1987/typos-skill with path . and name typos.
```

Restart Codex after installation, then ensure the scripts are executable if
your environment does not preserve executable bits:

```bash
SKILL_HOME="${CODEX_HOME:-$HOME/.codex}/skills/typos"
chmod +x "$SKILL_HOME/typos-skill.sh"
chmod +x "$SKILL_HOME/scripts/smoke-typos-skill.sh"
```

#### Manual Fallback Method

If your Codex environment does not expose `$skill-installer`, copy the skill
into the user skill directory manually:

```bash
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$SKILLS_DIR"
cp -r /path/to/typos-skill "$SKILLS_DIR/typos"
chmod +x "$SKILLS_DIR/typos/typos-skill.sh"
chmod +x "$SKILLS_DIR/typos/scripts/smoke-typos-skill.sh"
```

After either installation method, start a new Codex session in your target project and ask to use the skill:

```text
Use $typos to scan this repo, export review.jsonl, then apply approved corrections.
```

### Using `typos` in Codex

After installation, start a fresh Codex session in the target repository and invoke the skill explicitly with `$typos` or `typos`.

Common Codex prompts:

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

Typical Codex workflow:

1. Export suggestions with `--export-review review.jsonl`.
2. Review each item as `ACCEPT`, `FALSE POSITIVE`, or `CUSTOM`.
3. Apply approved fixes with `--apply-review review.jsonl`.
4. Re-run the skill if files changed during review to avoid offset conflicts.

### Skill Workflow Prompt (Both)

```text
Use the typos skill to:
1) run --export-review review.jsonl on docs/ and README.md
2) mark each finding as ACCEPT / FALSE POSITIVE / CUSTOM
3) apply with --apply-review review.jsonl
```

## 🛠️ Development

### Project Structure

```text
typos-skill/
├── SKILL.md              # Skill documentation
├── skill.json             # Skill metadata
├── typos-skill.sh         # Main script
├── scripts/
│   ├── apply-review.py    # Review application logic
│   └── smoke-typos-skill.sh  # Test script
├── agents/                # Agent configurations
└── .typos.toml            # Default typos configuration
```

### Running Tests

```bash
# Run smoke test
./scripts/smoke-typos-skill.sh

# Test with sample files
./typos-skill.sh --diff test/
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [typos](https://github.com/crate-ci/typos) - The fantastic spell checker
- [OpenClaw](https://github.com/openclaw/openclaw) - The AI agent platform
- All contributors who help improve this skill

## 📞 Support

- Issues: [GitHub Issues](https://github.com/luojiyin1987/typos-skill/issues)
- Discussions: [GitHub Discussions](https://github.com/luojiyin1987/typos-skill/discussions)

---

Made with care for the OpenClaw community.
