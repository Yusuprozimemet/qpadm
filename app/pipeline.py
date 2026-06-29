"""qpAdm pipeline orchestration.

Reproduces the steps of the original notebook but parameterised and runnable
outside Colab:

    1. plink  : 23andMe/LivingDNA text -> PLINK binary (.bed/.bim/.fam)
    2. plink  : --set-hh-missing  (zero out heterozygous haploid calls)
    3. convertf: PLINK -> EIGENSTRAT
    4. mergeit : merge the sample into the AADR reference panel
    5. patch the merged .ind so the target carries a clean population label
    6. qpAdm  : run the admixture model and capture the log
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Settings
from .models import QpAdmRequest, QpAdmResult
from .parsers import parse_qpadm_output

ProgressFn = Callable[[str, int], None]


class PipelineError(RuntimeError):
    """Raised when a pipeline step fails; carries the captured log."""

    def __init__(self, step: str, message: str):
        super().__init__(f"[{step}] {message}")
        self.step = step


@dataclass
class StepResult:
    name: str
    returncode: int
    log_path: Path


def _run(cmd: list[str], cwd: Path, log_path: Path, step: str) -> StepResult:
    """Run a subprocess, tee output to a log file, raise on failure."""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + " ".join(str(c) for c in cmd) + "\n\n")
        log.flush()
        proc = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if proc.returncode != 0:
        tail = _tail(log_path)
        raise PipelineError(step, f"exit code {proc.returncode}\n{tail}")
    return StepResult(step, proc.returncode, log_path)


def _tail(path: Path, n: int = 25) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def run_pipeline(
    genome_file: Path,
    req: QpAdmRequest,
    settings: Settings,
    job_dir: Path,
    progress: ProgressFn | None = None,
) -> QpAdmResult:
    """Execute the full pipeline in ``job_dir`` and return a parsed result."""

    def step(msg: str, pct: int) -> None:
        if progress:
            progress(msg, pct)

    env = settings.environment_report()
    if not env["pipeline_ready"]:
        missing = _missing_summary(env)
        raise PipelineError("preflight", f"environment not ready: {missing}")

    plink = settings.plink_path
    convertf = settings.tool_path("convertf")
    mergeit = settings.tool_path("mergeit")
    qpadm = settings.tool_path("qpAdm")
    ref = settings.reference_trio()

    label = _sanitize_label(req.sample_label)

    # --- 1. plink: 23andMe text -> bed ----------------------------------
    step("plink: import genotypes", 10)
    _run(
        [plink, "--23file", str(genome_file), label, "1", "--make-bed", "--out", "geno"],
        job_dir, job_dir / "01_plink_import.log", "plink-import",
    )

    # --- 2. plink: set heterozygous-haploid calls to missing ------------
    step("plink: clean haploid calls", 20)
    _run(
        [plink, "--bfile", "geno", "--set-hh-missing", "--make-bed", "--out", "geno_hh"],
        job_dir, job_dir / "02_plink_hh.log", "plink-hh",
    )

    # --- 3. convertf: PLINK -> EIGENSTRAT -------------------------------
    step("convertf: to EIGENSTRAT", 35)
    convert_par = job_dir / "convertf.par"
    convert_par.write_text(
        _par({
            "genotypename": job_dir / "geno_hh.bed",
            "snpname": job_dir / "geno_hh.bim",
            "indivname": job_dir / "geno_hh.fam",
            "outputformat": "EIGENSTRAT",
            "genotypeoutname": job_dir / "sample.geno",
            "snpoutname": job_dir / "sample.snp",
            "indivoutname": job_dir / "sample.ind",
        }),
        encoding="utf-8",
    )
    _run([convertf, "-p", convert_par], job_dir, job_dir / "03_convertf.log", "convertf")

    # --- 4. mergeit: merge into the reference panel ---------------------
    step("mergeit: merge with reference panel", 55)
    merge_par = job_dir / "merge.par"
    merge_par.write_text(
        _par({
            "geno1": ref["geno"], "snp1": ref["snp"], "ind1": ref["ind"],
            "geno2": job_dir / "sample.geno",
            "snp2": job_dir / "sample.snp",
            "ind2": job_dir / "sample.ind",
            "genooutfilename": job_dir / "merged.geno",
            "snpoutfilename": job_dir / "merged.snp",
            "indoutfilename": job_dir / "merged.ind",
            "outputformat": "EIGENSTRAT",
        }),
        encoding="utf-8",
    )
    _run([mergeit, "-p", merge_par], job_dir, job_dir / "04_mergeit.log", "mergeit")

    # --- 5. label the target individual ---------------------------------
    step("label target individual", 65)
    _label_target(job_dir / "merged.ind", req.target or label)

    # --- 6. qpAdm -------------------------------------------------------
    step("qpAdm: running model", 80)
    left_file = job_dir / "left.txt"
    right_file = job_dir / "right.txt"
    target = req.target or label
    left_file.write_text("\n".join([target, *req.sources]) + "\n", encoding="utf-8")
    right_file.write_text("\n".join(req.references) + "\n", encoding="utf-8")

    qpadm_par = job_dir / "qpadm.par"
    qpadm_par.write_text(
        _par({
            "genotypename": job_dir / "merged.geno",
            "snpname": job_dir / "merged.snp",
            "indivname": job_dir / "merged.ind",
            "popleft": left_file,
            "popright": right_file,
            "details": "YES",
            "allsnps": "YES" if req.allsnps else "NO",
        }),
        encoding="utf-8",
    )
    qpadm_log = job_dir / "06_qpadm.log"
    _run([qpadm, "-p", qpadm_par], job_dir, qpadm_log, "qpAdm")

    step("parsing results", 95)
    result = parse_qpadm_output(qpadm_log.read_text(encoding="utf-8", errors="replace"))
    # Trust the user-supplied config if the parser could not recover the lists.
    result.target = result.target or target
    result.sources = result.sources or req.sources
    result.references = result.references or req.references
    step("done", 100)
    return result


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _par(pairs: dict[str, object]) -> str:
    return "".join(f"{k}:\t{v}\n" for k, v in pairs.items())


def _sanitize_label(label: str) -> str:
    cleaned = "".join(ch for ch in label.strip() if ch.isalnum() or ch in "_-")
    return cleaned or "Sample"


def _label_target(ind_path: Path, pop_label: str) -> None:
    """Rewrite the last line of the merged .ind so the sample's population
    column equals ``pop_label`` (EIGENSTRAT .ind is: id  sex  population)."""
    lines = ind_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise PipelineError("label", f"empty .ind file: {ind_path}")
    last = lines[-1].split()
    ind_id = last[0] if last else pop_label
    sex = last[1] if len(last) > 1 else "U"
    lines[-1] = f"{ind_id}\t{sex}\t{pop_label}"
    ind_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _missing_summary(env: dict) -> str:
    parts = []
    missing_tools = [name for name, p in env["tools"].items() if not p]
    if missing_tools:
        parts.append("missing tools: " + ", ".join(missing_tools))
    if not env["reference_ready"]:
        miss = [ext for ext, p in env["reference"].items() if not p]
        parts.append("missing reference files: " + ", ".join(miss))
    return "; ".join(parts) or "unknown"
