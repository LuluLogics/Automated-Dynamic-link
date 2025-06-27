# Automated-Dynamic-Link

The **MWO-Virtuoso Regression Utility** is a Python automation tool that bridges the workflow between AWR Microwave Office (MWO) and Cadence Virtuoso VDL (Virtuoso Design Link). It streamlines launching both applications, establishing a connection, generating netlists, and performing regression testing by comparing generated netlists against reference versions. The tool features a batch mode that accepts a `.lst` script (the same format MWO uses internally) and runs every test listed, producing a simple, CI-friendly PASS/FAIL summary.


## 🚀 Purpose

This utility serves two main functions:

- **Continuous Integration Testing:** Ensures that new builds of MWO/VDL produce identical netlists to previous versions, maintaining consistent functionality across software updates.
- **Golden-Netlist Capture:** Generates and archives reference netlists to act as a baseline for future regression tests.


## 🛠️ Technical Architecture

- **Language:** Python
- **Interaction:** Orchestrates MWO and Virtuoso via process management and filesystem operations.

### Core Components

- **Runner class:** Handles environment setup, tool launch, netlist polling, capture/diff, and teardown for single projects.
- **BatchRunner:** Parses a single `.lst`, spins up Virtuoso once for the batch, restarts MWO per project, and collates results.
- **parse_lst():** Recursively parses `.lst` files for commands like `SET_PATH`, `LOAD_PROJECT`, `COMPARE_SAVED_MEAS`, and `INCLUDE_SCRIPT`.
- **Netlist polling:** Monitors `~/.awr/19.0/vdl/` for the first `vdl.scs` or `*.net` file.


## 🗂️ Key Workflow Steps

1. **Environment Preparation:** Sets `PATH`, `LM_LICENSE_FILE`, `CDS_LIC_FILE`, `MWO_ROOT`.
2. **Virtuoso Launch:** Runs one `virtuoso -replay` instance (remains active for batch runs).
3. **MWOffice Launch:** Initiates per project, with robust fallback mechanisms.
4. **Netlist Generation:** Waits for the VDL file (timeout configurable).
5. **Capture/Compare:**
    - **Capture:** Copies netlist to `./references/` (or `--out-dir`) with timestamp.
    - **Compare:** Uses `difflib.unified_diff` against reference, outputs `netlist_diff.txt` on failure.
6. **Teardown:** Always kills MWO between tests; can optionally shut down Virtuoso (`--shutdown`).


## 🖥️ Command Line Interface

Numerous CLI options allow you to customize operation:

| Option          | Description                                                        |
|-----------------|--------------------------------------------------------------------|
| `--capture`     | Run and save the newest netlist as a reference in `./references/`. |
| `--ref`         | Compare today’s netlist against a reference.                       |
| `--lst`         | Run every test in an MWO `.lst` (batch mode).                      |
| `--mwo-path` / `--vir-path` | Override default tool locations.                      |
| `--project`     | Run a single `.emp` (ignored if `--lst` is given).                 |
| `--workdir`     | Working directory for Virtuoso launch.                             |
| `--out-dir`     | Directory to store captured references (default `./references`).   |
| `--timeout`     | Seconds to wait for a netlist (default 60).                        |
| `--match`       | Only accept netlists whose filename contains a given string.       |
| `--shutdown`    | Terminate both tools on completion.                                |
| `--debug`       | Enable verbose DEBUG-level logging.                                |


## 💡 Typical Usage

### 1. Generate the `.lst`
```bash
cd /home/labraham/storage/MWO2/source/tests
bash genlst # creates all_tests.lst etc.
```

### 2. Capture golden netlist for the whole suite
```bash
python3 ADL.py \
  --lst /home/labraham/storage/MWO2/source/tests/all_tests.lst \
  --capture --timeout 90 --shutdown
```

### 3. Regression test in CI
```bash
python3 ADL.py \
  --lst /home/labraham/storage/MWO2/source/tests/all_tests.lst \
  --ref ./references/all_tests_20250530_120501.scs \
  --timeout 90 --shutdown
```

### 4. Ad-hoc single-project check
```bash
python3 ADL.py \
  --project /servers/awr_store/demo/testcase.emp \
  --capture
```


## 🔍 Netlist Comparison Logic

- **Comparison:** Exact line-by-line diff using `difflib.unified_diff`.
- **Preview:** Unified diff (first 3 lines) to console, full diff in `netlist_diff.txt`.
- **Exit Codes:**  
    - `0` = all pass  
    - `1` = one or more failures  
    - `2` = internal error  
- Fits standard CI expectations.


## ⚙️ Configuration

Default values are set at the top of the script but can be overridden via CLI:

```python
MWO_PATH = Path("/grid/cic/awr/V19/full/daily/latest")
VIR_PATH = Path("/grid/cic/IC25.1/dev/lnx86/64/latest_download")
VIRT_REPLAY = Path("/home/ffeltrin/vdl_launch.log")
PROJECT = Path("/servers/awr_store/ffeltrin/vdl_bus_bundle_not_working.emp")
WORKDIR = Path("/servers/awr_store/ffeltrin/sj_vdl")
OUT_DIR = Path("./references")
```

**Note:** The reference folder is now created in `$PWD/references` by default. Use `--out-dir` to override.


## 🔑 License Management

Environment variables are set for both tools:

```python
LIC_LM = "27005@sjflex4:5280@sjflex1"
LIC_CDS = "5280@sjflex1:5281@sjflex2"
```


## 📝 Logging

- **Console:** INFO by default; `--debug` enables DEBUG.
- **File:** By default, logs to `ADL.log`.
- Modify `logging.basicConfig` in the script if you need custom logging.


## ⚠️ Common Issues

- **FAIL after a capture:** Make sure to pass the newest reference file on the next run.
- **Timeout waiting for netlist:** Increase `--timeout` or verify MWO finished simulation.
- **License checkout errors:** Confirm `LM_LICENSE_FILE` and `CDS_LIC_FILE`.


## 🚧 Future Enhancements

- GUI automation hooks (e.g., PyAutoGUI) for full wizard dialog coverage.
- Smarter diff options to ignore comments, timestamps, or non-functional text.


## 🙏 Acknowledgements

- Implementation guided by @Francesco-Feltrin & manually refactored by @AWR-Intern.


**2025-05-27 – script v2 highlights:**

- New CLI overrides: `--mwo-path`, `--vir-path`, `--project`, `--workdir`, `--out-dir`, `--match`.
- Robust AWR launcher with fallback.
- Reference folder location improvements.
- Filename filter via `--match`.
- No `os.chdir` side-effects.

---
