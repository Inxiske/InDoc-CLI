# InDoc-CLI

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Status-Stable-brightgreen.svg" alt="Status">
  <img src="https://img.shields.io/badge/Powered%20by-Ollama-orange.svg" alt="Ollama">
</p>

<p align="center">
  <strong>Local-first forensic code auditing.</strong><br>
  InDoc-CLI scans your local project and generates documentation artifacts locally.
</p>

---

## Why InDoc-CLI?

- **Total Privacy**: Your code never leaves your machine. All processing is done locally via Ollama.
- **Lightning Fast**: Just type `inx scan .` and get a complete architecture analysis of your project in seconds.
- **Context-Aware**: InDoc-CLI understands your project's structure and generates meaningful documentation.
- **Intelligent**: Powered by local LLMs (Llama3), it provides deep architectural insights, not just code comments.
- **Zero Dependencies**: No cloud accounts, no API keys, no monthly fees.

---

## Features

### The `inx scan` Command (Project Intelligence)

Scan your entire project recursively and generate an architectural overview:

```bash
inx scan ./my-project
```

This will:
1. Crawl the project directory
2. Identify all code files (.py, .js, .cpp, etc.)
3. Generate a **Project Map** (Language | Files | Size table)
4. Send the architecture summary to Ollama for intelligent analysis
5. Return a comprehensive project documentation

### Smart Ignore System

InDoc-CLI is git-aware and respects `.gitignore`. If `.gitignore` does not exist, it falls back to `indoc.ignore`.

```gitignore
# .docgenignore
my-secret-folder
internal-notes/
```

InDoc-CLI automatically ignores common directories like `node_modules`, `venv`, `__pycache__`, `.git`, and `dist`.

### Rich Terminal Output

Beautiful, structured output using Rich library:

- **Project Maps**: Clean tables showing language distribution
- **Markdown Rendering**: Professional documentation formatting
- **Progress Indicators**: Real-time feedback during processing

---

## Installation

### Prerequisites

- **Python 3.10+**
- **Ollama** ([Download here](https://ollama.com))

### Quick Install

```bash
# Clone the repository
git clone https://github.com/inxiske/indoc-cli.git
cd indoc-cli

# Install dependencies
pip install rich ollama

# Download the Llama3 model
ollama run llama3

# Run the tool
python cli.py
```

---

## Usage

```
(inx) username@system > inx help
```

### Command Reference

| Command | Description |
|---|---|
| `inx gen <file>` | Generate documentation for a single file |
| `inx scan <dir>` | Scan entire project recursively |
| `inx status` | Check Ollama connection status |
| `inx install ollama` | Open Ollama setup options |
| `inx identity` | Show build and developer information |
| `inx about` | About InDoc-CLI |
| `inx clear` | Clear terminal |
| `inx dev` | Developer greeting |
| `exit` | Terminate session |

---

## Project Structure

```
indoc-cli/
├── main.py          # Main CLI entrypoint
├── cli/             # Command implementations
├── core/            # Engine + scanner modules
├── build_cli.py    # PyInstaller build script
├── indoc.ignore     # Ignore patterns (optional fallback)
└── dist/
    └── InDoc-CLI.exe       # Compiled executable
```

---

## Technical Details

- **Language**: Python 3.10+
- **UI Framework**: Rich Library
- **AI Backend**: Ollama (Llama3)
- **Build Tool**: PyInstaller
- **License**: MIT

---

## Maintained by Inxiske Engineering

InDoc-CLI is developed and maintained by **Inxiske Engineering**.

For questions, bug reports, or feature requests, please open an issue on GitHub.

---

<p align="center">
  <strong>InDoc-CLI</strong>  Code Analysis & Documentation, Locally.<br>
  <em>Privacy-first. Speed-second-to-none. Built for developers.</em>
</p>
