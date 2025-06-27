# Vb2Py - Visual Basic ⇒ Python Conversion

**Vb2Py.py** is a hand-ported, modern-Python replacement for a 7,000+ line Visual Basic macro originally used inside Keysight/AWR Microwave Office projects.  
The goal is to keep the behaviour 100% identical while replacing out-of-date VB patterns with maintainable, testable Python 3 code.

## ✨ Key Features

| Area             | What changed vs. VB                                         |
|------------------|-------------------------------------------------------------|
| Datatypes        | VB's `Type` blocks → Python `@dataclass`                    |
| Globals & flags  | Explicit module-level variables, fully typed                |
| Dialogs          | Stubbed (`show_dialog`) for CLI use; drop-in GUI (Tkinter/PySimpleGUI) later |
| Filesystem       | VB Scripting.FileSystemObject → Python `os`, `pathlib`, `shutil` |
| Process control  | VB `ShellWait` rewritten with `subprocess.Popen` + `proc.wait()`   |
| Timing/logging   | `<DateDiff>` etc. swapped for `datetime` + rich logging (TBD)      |
| Error handling   | Structured `try/except`; placeholder `error_handler()` for future central handling |
| Unit-testability | Functions side-effect-free where practical; stubs replace external AWR API calls |


## 📦 Installation

```bash
git clone https://github.com/<YOUR-GH-USER>/vb2py-script.git
cd vb2py-script
python -m venv .venv && source .venv/bin/activate  # optional but recommended
pip install -r requirements.txt                    # currently only std-lib needed
# (If you only need to read the script, a browser is fine; no install.)
```

## 🚀 Quick Start

```bash
python Vb2Py.py --help         # CLI help once argument-parsing is hooked up
python Vb2Py.py                # runs default export-check dialog in console
```
*Heads-up: most UI is still stubbed.*  
Core routines (`export_check()`, `check_and_fix_pdk()`, …) are fully functional for batch-style invocation.


## 🗺️ Project Layout

```
.
├── Vb2Py.py          ← the translated script
├── docs/             ← GitHub Pages (architecture notes, how-to guides)
├── tests/            ← pytest unit tests (WIP)
└── README.md
```

## 🛠️ Development

```bash
# lint & style-check
ruff check Vb2Py.py
black --check Vb2Py.py

# run unit tests
pytest -q
```

**Contributing**
1. Fork → Create feature branch → Commit → Open Pull Request
2. Ensure pytest, ruff, and black pass in CI.
3. PR template will prompt for a short change-log entry.

## 📑 Roadmap

- [ ] Replace dialog stubs with Tkinter UI
- [ ] Full logging via `logging.config.dictConfig`
- [ ] Continuous export-check regression tests (GitHub Actions, sample AWR projects)
- [ ] Switch file paths to `pathlib.Path` everywhere
- [ ] Auto-generate CLI from stubs with [typer](https://typer.tiangolo.com/)


## 🙏 Acknowledgements

- Original VB macro by Cadence / AWR internal tooling team.
- Conversion guided by ChatGPT (o3), manual refactor by @<your name>.
- Icons from Twemoji (CC-BY 4.0).


## ⚖️ License

Distributed under the MIT License.  
See [LICENSE](LICENSE) for details.


> **Where to edit:**  
> • Replace every `<YOUR-GH-USER>` with your real GitHub username.  
> • Replace `<your name>` in Acknowledgements.  
> • Swap MIT badge/section if you’ll use another license.  
> • Trim the *Roadmap* / *Acknowledgements* to match reality.

```bash
git add README.md
git commit -m "docs: add project README"
git push
```
