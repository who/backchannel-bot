# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## AI Guidance

* After receiving tool results, carefully reflect on their quality and determine optimal next steps before proceeding.
* For maximum efficiency, invoke multiple independent operations simultaneously rather than sequentially.
* Before you finish, verify your solution.
* Do what has been asked; nothing more, nothing less.
* NEVER create files unless absolutely necessary for achieving your goal.
* ALWAYS prefer editing an existing file to creating a new one.
* NEVER proactively create documentation files (*.md) or README files unless explicitly requested.

## Work Execution Policy

**All implementation work MUST go through Ralph loops.**

When asked to implement features, fix bugs, or make code changes:

1. **Do NOT implement directly** - Instead, create beads issues with detailed descriptions
2. **Create well-structured issues** - Use `bd create` with clear titles, descriptions, and acceptance criteria
3. **Set up dependencies** - Use `bd dep add` to establish proper ordering
4. **Defer to Ralph** - The `ralph.sh` loop will execute the actual work via ortus/prompts/ralph-prompt.md

**Allowed without Ralph loop:**
- Answering questions about the codebase
- Reading/exploring files for research
- Creating beads issues
- Discussing architecture or approach

**Requires Ralph loop:**
- Writing or modifying code
- Creating new files
- Running tests or builds
- Any implementation work

This ensures all work is tracked, atomic, and follows the defined workflow.

## Project Overview

A hacky discord back channel communication from discord to your Claude tmux session

## Technology Stack

- **Language**: Python
- **Package Manager**: uv
- **Linter**: ruff

## Development Guidelines

### Code Standards
* Type hints required for all functions
* Use Pydantic models for data validation
* Follow Google Python Style Guide
* Use `ruff` for linting and formatting
* Use `uv` for dependency management (not pip)

### Before Committing
1. Run `uv run ruff check .` and `uv run ruff format .`
2. Run `uv run pytest` if tests exist
3. Stage changes appropriately

## Command Reference

### Development
```bash
# Setup (first time)
uv sync                              # Install all dependencies
uv venv                              # Create virtual environment (if needed)

# Run development server
uv run python -m app.main

# Run tests
uv run pytest

# Linting
uv run ruff check .
uv run ruff format .

# Add dependencies
uv add <package>                     # Add to main dependencies
uv add --dev <package>               # Add to dev dependencies
```

### File Operations - Use Fast Tools

```bash
# List files (FAST)
fd . -t f           # All files recursively
rg --files          # All files (respects .gitignore)
fd . -t d           # All directories

# Search content (FAST)
rg "search_term"                # Search in all files
rg -i "case_insensitive"        # Case-insensitive
rg "pattern" -g "*.ext"         # Only specific file type
rg -l "pattern"                 # Filenames with matches
rg -c "pattern"                 # Count matches per file
rg -n "pattern"                 # Show line numbers
rg -A 3 -B 3 "pattern"          # Context lines

# Find files by name (FAST)
fd "filename"                   # Find by name pattern
fd -e ext                       # All files with extension
```

### Banned Commands - Avoid These Slow Tools

* `tree` - use `fd` instead
* `find` - use `fd` or `rg --files`
* `grep` or `grep -r` - use `rg` instead
* `ls -R` - use `rg --files` or `fd`
* `cat file | grep` - use `rg pattern file`

### Search Strategy

1. Start broad, then narrow: `rg "partial" | rg "specific"`
2. Filter by type early: `rg "pattern" -g "*.ext"`
3. Batch patterns: `rg "(pattern1|pattern2|pattern3)"`
4. Limit scope: `rg "pattern" src/`

## Project Architecture

### File Structure

```
backchannel-bot/
├── src/                      # Source code
├── tests/                    # Test suite (optional)
├── prd/                      # Product requirements documents
├── .beads/                   # Issue tracking
├── .claude/                  # Claude Code settings
└── CLAUDE.md                 # This file
```

## Issue Tracking

This project uses **beads** (`bd`) for issue tracking. See **AGENTS.md** for workflow and session protocol.

### Beads Visualization

View your issues in a visual interface:
- [bdui](https://github.com/assimelha/bdui) - Web-based beads visualization

Or use the CLI:
```bash
bd list              # List all issues
bd ready             # Show issues ready to work
bd stats             # Project statistics
```

## Important Files

* **CLAUDE.md** - AI agent instructions (this file)
* **AGENTS.md** - Session rules and landing-the-plane protocol
* **ortus/prompts/** - All prompt files (ralph-prompt.md, interview-prompt.md, prd-prompt.md)
* **ortus/ralph.sh** - Task implementation loop
* **ortus/interview.sh** - Interactive feature interview with Claude

## Pro Tips for AI Agents

* Always use `--json` flags when available for programmatic use
* Use dependency trees to understand complex relationships
* Higher priority issues (0-1) are usually more important than lower (2-4)
