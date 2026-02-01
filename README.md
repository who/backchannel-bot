# backchannel-bot

A hacky discord back channel communication from discord to your Claude tmux session

## Tech Stack

- **Language**: Python
- **Package Manager**: uv
- **Linter**: ruff

## Quick Start

```bash
# Install dependencies
uv sync

# Run the project
uv run python -m app.main

# Run tests
uv run pytest

# Lint code
uv run ruff check .
uv run ruff format --check .
```

## Workflow

This project uses beads (`bd`) for issue tracking and Ralph automation loops for implementation.

### Kickstart Your Feature

Run `./ortus/idea.sh` to start. You'll be asked whether you have a PRD or just an idea:

**Option 1: You have a PRD (non-interactive)**
```bash
./ortus/idea.sh --prd path/to/your-prd.md
```
Your PRD will be automatically decomposed into a beads issue graph:
- Creates an epic with hierarchical implementation tasks
- Sets up proper dependencies between issues
- Uses parallel sub-agents for efficient issue creation
- Runs in automated mode (no permission prompts)

**Option 1b: You have a PRD (interactive)**
```bash
./ortus/idea.sh
# Choose [1] "Yes, I have a PRD"
# Provide the path to your PRD file
```

**Option 2: You have an idea**
```bash
./ortus/idea.sh "Your feature idea"
# Or run ./ortus/idea.sh and choose [2] "Nope, just an idea"
```
Claude will:
1. Expand your idea into a feature description
2. Run an interactive interview to clarify requirements
3. Generate a PRD document
4. Create implementation tasks from the PRD

### Implement with Ralph

Once tasks exist, run the implementation loop:

```bash
./ortus/ralph.sh
```

Ralph picks up tasks and implements them one by one, running tests and committing changes.

### Issue Tracking Commands

```bash
bd list              # List all issues
bd ready             # Show issues ready to work
bd show <id>         # View issue details
bd stats             # Project statistics
```

## Project Structure

```
backchannel-bot/
├── src/                  # Source code
│   └── app/              # Application package
├── tests/                # Test suite
├── ortus/                # Ortus automation scripts and prompts
│   └── prompts/          # AI prompt templates
├── prd/                  # Product requirements documents
├── .beads/               # Issue tracking data
└── .claude/              # Claude Code settings
```

## Repository

[who/backchannel-bot](https://github.com/who/backchannel-bot)

## License

MIT
