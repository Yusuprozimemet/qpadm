"""Tests for the qpAdm log parser."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers import parse_qpadm_output  # noqa: E402

SAMPLE_LOG = """\
qpAdm: parameter file: qpadm.par
left pops:
Sample
Iran_GanjDareh_N
Russia_MLBA_Sintashta

right pops:
Mbuti.DG
Russia_Ust_Ishim_HG.DG
Karitiana.DG
Ami.DG

jackknife block size:     0.050
snps: 1150639  indivs: 12
coverage check ...
best coefficients:     0.412   0.588
      std. errors:     0.034   0.041

fixed pat  wt  dof  chisq  tail prob
00         0   2    1.234  0.539821   0.412 0.588
01         1   3    9.870  0.019733   1.000 0.000
10         1   3    8.110  0.043765   0.000 1.000

summ: Sample  2  0.539821  0.412 0.588
"""


def test_parse_basic():
    r = parse_qpadm_output(SAMPLE_LOG)
    assert r.target == "Sample"
    assert r.sources == ["Iran_GanjDareh_N", "Russia_MLBA_Sintashta"]
    assert r.references == ["Mbuti.DG", "Russia_Ust_Ishim_HG.DG", "Karitiana.DG", "Ami.DG"]


def test_parse_coefficients():
    r = parse_qpadm_output(SAMPLE_LOG)
    weights = {c.source: c.weight for c in r.coefficients}
    assert weights["Iran_GanjDareh_N"] == 0.412
    assert weights["Russia_MLBA_Sintashta"] == 0.588
    errs = {c.source: c.std_error for c in r.coefficients}
    assert errs["Iran_GanjDareh_N"] == 0.034


def test_p_value_and_feasibility():
    r = parse_qpadm_output(SAMPLE_LOG)
    assert abs(r.p_value - 0.539821) < 1e-9
    assert r.feasible is True


def test_models_table():
    r = parse_qpadm_output(SAMPLE_LOG)
    assert len(r.models) == 3
    assert r.models[0]["pattern"] == "00"


def test_infeasible_when_low_p():
    log = SAMPLE_LOG.replace("tail prob\n00         0   2    1.234  0.539821",
                             "tail prob\n00         0   2    1.234  0.001000")
    log = log.replace("summ: Sample  2  0.539821", "summ: Sample  2  0.001000")
    r = parse_qpadm_output(log)
    assert r.p_value < 0.05
    assert r.feasible is False


def test_empty_input():
    r = parse_qpadm_output("")
    assert r.coefficients == []
    assert r.target is None


if __name__ == "__main__":
    import traceback

    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    sys.exit(1 if failed else 0)
