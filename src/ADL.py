#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
mwo_virtuoso_test.py – capture / diff Spectre® netlists (single project or .lst batch)
 
───────────────────────────────────────────────────────────────────────────────
Quick start:
Generate netlists for projects "all_test.lst" and saves them to ./refereces
    $> python ADL.py --capture --lst /servers/awr_store/ffeltrin/sampleVDLTest/all_tests.lst --timeout 90
Generate netlist for projects in "all_test.lst" and compare them with netlist in ./references (matched by name)
    $> python ADL.py --lst /servers/awr_store/ffeltrin/sampleVDLTest/all_tests.lst --timeout 90
 
Details about flags
• --capture         → copies newest *vdl.scs / *.net* into ./references/
    if --capture not defined → "compare mode": diffs today’s netlist against the reference
• --match <str>     → filename substring that *must* be in the chosen netlist
• --lst <file>      → iterate over a MWOffice <file>.lst and run each test
• --shutdown        → close tools when done (default: keep open)
 
For a .lst batch run the script behaves as follows:
 
   1. The .lst is parsed (recursively if INCLUDE_SCRIPT directives are found).
   2. Virtuoso is launched **once** and kept alive for the whole batch.
   3. For every    SET_PATH / LOAD_PROJECT / COMPARE_SAVED_MEAS trio the tool:
        • launches MWOffice on the *.emp project,
        • waits for the generated vdl netlist,
        • diffs it against the reference schematic (matched by name, in /refereces folder) or captures it (if --capture),
        • kills AWRDE, and proceeds with the next project.
   4. A summary table of PASS / FAIL is printed at the end, and exit status is 0 if all passed, 1 otherwise.
"""
 
from __future__ import annotations
import argparse
import difflib
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
 
# ─────────────────────────────────────────────────────────────────────────────
# Default site configuration
# ─────────────────────────────────────────────────────────────────────────────
MWO_PATH    = Path("/grid/cic/awr/V19/full/daily/latest")
VIR_PATH    = Path("/grid/cic/IC25.1/dev/lnx86/64/latest_download")
VIRT_REPLAY = Path(__file__).parent / "vdl_launch.log" # use relative path for virtuoso replay script in this repo
PROJECT     = Path("/servers/awr_store/ffeltrin/vdl_bus_bundle_not_working.emp")
WORKDIR     = Path("/servers/awr_store/ffeltrin/sj_vdl")
 
# Save references in the current working directory
OUT_DIR     = Path.cwd() / "references"
LM, CDS = "27005@sjflex4:5280@sjflex1", "5280@sjflex1:5281@sjflex2"


# ────────────────────────────────────────────────────────────────────────────
# Logging  (console + file)
# ────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
 
log = logging.getLogger(__name__)
 
 
# ═══════════════════════════════════════════════════════════════════════════
# Helper – parse *.lst script into absolute (emp, prt) tuples
# ═══════════════════════════════════════════════════════════════════════════
LST_CMD_PAT = re.compile(r"^(SET_PATH|LOAD_PROJECT|COMPARE_SAVED_MEAS|INCLUDE_SCRIPT)\s+(.*)$")
 
 
def parse_lst(lst_path: Path) -> List[Tuple[Path, Path]]:
    """Return list of (emp_path, prt_path) pairs found in *lst_path* (recursive)."""
 
    emp_prt_pairs: List[Tuple[Path, Path]] = []
 
    cwd: Path | None = None
 
    pending_emp: Optional[str] = None
 
 
    def _abs(path_str: str) -> Path:
 
        p = Path(path_str)
 
        if p.is_absolute():
 
            return p
 
        if cwd is None:
 
            raise ValueError(f"Relative path '{p}' encountered before SET_PATH in {lst_path}")
 
        return (cwd / p).resolve()
 
    with lst_path.open() as fp:
 
        for raw in fp:
 
            line = raw.strip()
 
            if not line or line.startswith("#"):
 
                continue
 
            m = LST_CMD_PAT.match(line)
 
            if not m:
 
                continue
 
            cmd, arg = m.groups()
 
            if cmd == "SET_PATH":
 
                cwd = Path(arg.rstrip("/ ")).expanduser().resolve()
 
            elif cmd == "INCLUDE_SCRIPT":
 
                include_file = _abs(arg)
 
                emp_prt_pairs.extend(parse_lst(include_file))
 
            elif cmd == "LOAD_PROJECT":
 
                pending_emp = _abs(arg).as_posix()
 
            elif cmd == "COMPARE_SAVED_MEAS":
 
                if pending_emp is None:
 
                    raise ValueError(f"COMPARE_SAVED_MEAS without preceding LOAD_PROJECT in {lst_path}")
 
                prt = _abs(arg)
 
                emp_prt_pairs.append((Path(pending_emp), prt))
 
                pending_emp = None
 
    return emp_prt_pairs
 
 
# ═══════════════════════════════════════════════════════════════════════════
# Main driver for a *single* project netlisting
# ═══════════════════════════════════════════════════════════════════════════
class Runner:
 
    def __init__(self,
                 
                 *,
                 
                 ref: Optional[Path],
                 
                 capture: bool,
 
                 timeout: int,
                 
                 shutdown: bool,
 
                 match: Optional[str],
 
                 virt_proc: Optional[subprocess.Popen[str]] = None,
 
                 project: Optional[Path] = None) -> None:
 
        self.ref, self.capture, self.timeout = ref, capture, timeout
 
        self.shutdown, self.match = shutdown, match
 
        self.project = project or PROJECT
 
        self.proj_name = self.project.stem
 
        # ─── dynamically pick the latest 19.x directory ───
 
        awr_base = Path.home() / ".awr"
 
        versions = sorted(
 
            (p for p in awr_base.iterdir() if p.is_dir() and p.name.startswith("19.")),
 
            key=lambda p: p.name, reverse=True
 
        )
 
        version_dir = versions[0] if versions else awr_base / "19.0"
 
        self.root = version_dir / "vdl" / self.proj_name
 
        self.vir: Optional[subprocess.Popen[str]] = virt_proc
 
        self.mwo: Optional[subprocess.Popen[str]] = None
 
 
    def run(self) -> int:
 
        try:
 
            self._set_env()
 
            self._purge_stale_netlists()
 
            if self.vir is None:
 
                self._start_virt()
 
            self._start_mwo()
 
            net = self._wait_netlist()
 
            return self._capture(net) if self.capture else (0 if self._compare(net) else 1)
 
        except Exception as exc:
 
            log.exception("
￼
 %s", exc)
 
            return 2
 
        finally:
 
            self._teardown()
 
    # ──────────────────────────────────────────────────────────────
    #  Launch helpers
    # ──────────────────────────────────────────────────────────────
    def _set_env(self) -> None:
 
        os.environ["PATH"] = f"{MWO_PATH}/bin:{VIR_PATH}/bin:{os.environ['PATH']}"
        os.environ["LM_LICENSE_FILE"], os.environ["CDS_LIC_FILE"] = LM, CDS
 
        # Let Virtuoso replay resolve awrVDL.ile relative to MWO_ROOT
        os.environ["MWO_ROOT"] = str(MWO_PATH)
 
 
    def _purge_stale_netlists(self) -> None:
 
        if not self.root.exists():
 
            return
 
        removed = 0
 
        for f in self.root.rglob("*"):
 
            if (f.suffix in (".scs", ".net") and (self.match is None or self.match in f.name)):
 
                try:
 
                    f.unlink(); removed += 1
 
                except OSError:
 
                    pass
 
        if removed:
 
            log.debug("Purged %d stale netlist(s) from %s", removed, self.root)
 
 
    def _start_virt(self) -> None:
 
        self.vir = subprocess.Popen(
 
            ["virtuoso", "-replay", str(VIRT_REPLAY)],
 
            cwd=WORKDIR,
            
            stdout=subprocess.DEVNULL,
            
            stderr=subprocess.DEVNULL)
 
        log.info("✓ Virtuoso PID %s", self.vir.pid)
 
 
    def _start_mwo(self) -> None:
 
        candidates = [MWO_PATH / "bin" / exe for exe in ("awrde_ui", "awrde")]
 
        for exe in candidates:
 
            if exe.exists():
 
                cmd = ([str(exe), str(self.project)] if os.access(exe, os.X_OK)
 
                       else ["/bin/sh", "-c", f"'{exe}' '{self.project}'"])
 
                self.mwo = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
 
                log.info("✓ AWRDE  PID %s  (launcher: %s)", self.mwo.pid, exe.name)
 
                return
 
        raise FileNotFoundError(f"No AWRDE launcher found under {MWO_PATH}/bin")
 
 
    # ───────────────────────────────────────────────────────────────
    #  Netlist polling
    # ───────────────────────────────────────────────────────────────
    def _wait_netlist(self) -> Path:
 
        log.info("Waiting %s s for *vdl* netlist under %s …", self.timeout, self.root)
 
        seen: set[Path] = set(); start = time.time()
 
        while time.time() - start < self.timeout:
 
            for f in self.root.rglob("*"):
 
                if f in seen:
 
                    continue
 
                seen.add(f)
 
                if (f.suffix in (".scs", ".net") and "vdl" in f.name
 
                        and (self.match is None or self.match in f.name)):
 
                    log.info("→ Netlist: %s", f)
 
                    return f
 
            time.sleep(1)
 
        raise TimeoutError("No matching vdl.scs / *.net within timeout")
 
 
    # ──────────────────────────────────────────────────────────────
    #  Capture / Compare
    # ──────────────────────────────────────────────────────────────
    def _capture(self, net: Path) -> int:
 
        OUT_DIR.mkdir(parents=True, exist_ok=True)
 
        dst = OUT_DIR / f"{self.proj_name}_reference{net.suffix}"
 
        if dst.exists():
 
            log.info("Overwriting existing reference %s", dst)
 
        shutil.copy2(net, dst)
 
        log.info("
￼
 Reference saved → %s", dst)
 
        log.info("Run regression without --capture to compare against this file")
 
        return 0
 
 
    def _compare(self, net: Path) -> bool:
        '''
            # I’ve replaced the _compare logic so that:
            # •              It ignores the .prt if you’ve recorded a .scs with the same base name.
            # •              It falls back to scanning your references/ folder for any proj_name*.scs, picking the newest.
            # •              If no .scs is found, it errors out.
        '''
        # locate reference schematic in references folder
        ref_candidates = list(OUT_DIR.glob(f"{self.proj_name}_reference*.scs"))
 
        if not ref_candidates:
 
            ref_candidates = list(OUT_DIR.glob(f"{self.proj_name}_reference*.net"))
 
        if not ref_candidates:
 
            raise FileNotFoundError(f"No reference schematic found in {OUT_DIR} for project '{self.proj_name}'")
 
        ref_candidates.sort()
 
        ref = ref_candidates[-1]
 
        log.debug("Using reference file %s", ref)
 
        # read and diff
 
        lhs = ref.read_text().splitlines(1)
 
        rhs = net.read_text().splitlines(1)
 
        diff = list(difflib.unified_diff(lhs, rhs, fromfile=str(ref), tofile=str(net)))
 
        if diff:
 
            Path("netlist_diff.txt").write_text("".join(diff))
 
            log.error("
￼
 FAIL – netlists differ (see netlist_diff.txt)")
 
            log.error("First 3 diff lines:%s", "".join(diff[:3]))
 
            return False
 
        log.info("
￼
 PASS – netlists identical")
 
        return True
 
 
    # ───────────────────────────────────────────────────────────────
    #  Optional shutdown
    # ───────────────────────────────────────────────────────────────
    def _teardown(self) -> None:
 
        if self.shutdown:
 
            if self.mwo and self.mwo.poll() is None:
 
                log.info("Terminating AWRDE …")
 
                self.mwo.send_signal(signal.SIGTERM)
 
                try:
 
                    self.mwo.wait(timeout=5)
 
                except subprocess.TimeoutExpired:
 
                    self.mwo.kill()
 
        else:
 
            log.debug("AWRDE left running (shutdown flag not set).")
 
 
# ════════════════════════════════════════════════════════════════════════════
# Batch driver for .lst files
# ════════════════════════════════════════════════════════════════════════════
class BatchRunner:
 
    def __init__(self, lst_file: Path, *, capture: bool, timeout: int,
 
                 shutdown: bool, match: Optional[str]):
 
        self.lst_file = lst_file
 
        self.capture = capture; self.timeout = timeout
 
        self.shutdown, self.match = shutdown, match
 
        self.tests = parse_lst(lst_file)
 
        if not self.tests:
 
            raise ValueError(f"No tests found in {lst_file}")
 
        log.info("Parsed %d test(s) from %s", len(self.tests), lst_file)
 
 
    def run(self) -> int:
       
        virt_proc: Optional[subprocess.Popen[str]] = None
 
        summary: List[Tuple[str, str]] = []
 
        failed = 0
 
        try:
 
            for emp, prt in self.tests:
 
                log.info("════════════════════════════════════════════════════")
 
                log.info("
￼
 Test: %s", emp.name)
 
                runner = Runner(ref=(None if self.capture else prt), capture=self.capture,
 
                                timeout=self.timeout, shutdown=True,
 
                                match=self.match, virt_proc=virt_proc, project=emp)
 
                rc = runner.run()
 
                if virt_proc is None:
 
                    virt_proc = runner.vir
 
                status = "PASS" if rc == 0 else "FAIL"
 
                summary.append((emp.name, status))
 
                if status == "FAIL": failed += 1
 
        finally:
 
            if self.shutdown and virt_proc and virt_proc.poll() is None:
 
                log.info("Shutting down shared Virtuoso …")
 
                virt_proc.send_signal(signal.SIGTERM)
 
                try: virt_proc.wait(timeout=5)
 
                except subprocess.TimeoutExpired: virt_proc.kill()
 
        log.info("════════════════════════ SUMMARY ══════════════════════")
 
        width = max(len(name) for name, _ in summary) if summary else 10
 
        for name, status in summary:
 
            log.info(f"{name:<{width}} : {status}")
 
        log.info("%d / %d test(s) failed", failed, len(summary))
 
        return 0 if failed == 0 else 1
 
 
# ════════════════════════════════════════════════════════════════════════════
# CLI glue
# ════════════════════════════════════════════════════════════════════════════
def parse_cli() -> argparse.Namespace:
    global MWO_PATH, VIR_PATH, PROJECT, WORKDIR, OUT_DIR
 
    ap = argparse.ArgumentParser()
    # capture vs compare: --capture enables capture, no flag = compare mode
    ap.add_argument("--capture", action="store_true",
                    help="capture golden netlist into ./references/")
    # allow explicit ref for single-run compare
    ap.add_argument("--ref", type=Path,
                    help="compare against reference file (single project only)")
 
    # path overrides
    ap.add_argument("--mwo-path", type=Path)
    ap.add_argument("--vir-path", type=Path)
    ap.add_argument("--project", type=Path,
                    help="single *.emp project to run")
    ap.add_argument("--workdir", type=Path)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
 
    # batch option
    ap.add_argument("--lst", type=Path,
                    help="run a MWOffice .lst batch script")
 
    # misc
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--match", type=str)
    ap.add_argument("--shutdown", action="store_true",
                    help="shutdown AWRDE when done")
    ap.add_argument("--debug", action="store_true")
 
    ns = ap.parse_args()
 
    # apply overrides
    if ns.mwo_path:
        MWO_PATH = ns.mwo_path
 
    if ns.vir_path:
        VIR_PATH = ns.vir_path
 
    if ns.project:
        PROJECT = ns.project
 
    if ns.workdir:
        WORKDIR = ns.workdir
 
    OUT_DIR = ns.out_dir
 
    # default levels
    if ns.debug:
        logging.getLogger().setLevel(logging.DEBUG)
 
    return ns
 
 
if __name__ == "__main__":
 
    args = parse_cli()
 
    if args.lst:
 
        exit_code = BatchRunner(
 
            args.lst,
 
            capture=args.capture,
 
            timeout=args.timeout,
 
            shutdown=args.shutdown,
 
            match=args.match
 
        ).run()
 
    else:
 
        exit_code = Runner(
 
            ref=(None if args.capture else args.ref),
 
            capture=args.capture,
           
            timeout=args.timeout,
           
            shutdown=args.shutdown,
           
            match=args.match
        ).run()
   
    sys.exit(exit_code)
 
     
