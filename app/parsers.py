"""Parsers for AdmixTools qpAdm output.

The output format varies a little between AdmixTools versions, so the parser is
deliberately tolerant: it pulls out the pieces it recognises and always keeps
the raw text around for transparency.
"""
from __future__ import annotations

import re

from .models import Coefficient, QpAdmResult

_FLOAT = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


def _floats(line: str) -> list[float]:
    return [float(x) for x in re.findall(_FLOAT, line)]


def _parse_pop_block(text: str, header: str) -> list[str]:
    """Read a ``left pops:`` / ``right pops:`` style block.

    The block is the run of non-empty, single-token lines that follows the
    header up to the first blank line or a line that is clearly not a pop name.
    """
    pops: list[str] = []
    capture = False
    for raw in text.splitlines():
        line = raw.strip()
        if not capture:
            if line.lower().startswith(header):
                capture = True
            continue
        if not line:
            break
        # A pop name is a single whitespace-free token; anything else ends it.
        if len(line.split()) != 1:
            break
        pops.append(line)
    return pops


def parse_qpadm_output(text: str) -> QpAdmResult:
    """Parse a qpAdm log into a structured result."""
    result = QpAdmResult(raw_output=text)

    left = _parse_pop_block(text, "left pops")
    right = _parse_pop_block(text, "right pops")
    result.references = right
    if left:
        result.target = left[0]
        result.sources = left[1:]

    coeffs: list[float] = []
    errors: list[float] = []
    for raw in text.splitlines():
        low = raw.lower()
        if "best coefficients" in low:
            coeffs = _floats(raw)
        elif "std. errors" in low or "std errors" in low:
            errors = _floats(raw)

    # Match coefficients to source pops where possible.
    sources = result.sources or [f"source{i + 1}" for i in range(len(coeffs))]
    for i, w in enumerate(coeffs):
        se = errors[i] if i < len(errors) else None
        label = sources[i] if i < len(sources) else f"source{i + 1}"
        result.coefficients.append(Coefficient(source=label, weight=w, std_error=se))

    result.p_value = _extract_p_value(text)
    if result.p_value is not None:
        # Conventional qpAdm reading: model is plausible if p > 0.05 and all
        # weights are within [0, 1] (no large negative/over-unity coefficients).
        feasible_weights = all(-0.05 <= c.weight <= 1.05 for c in result.coefficients)
        result.feasible = result.p_value > 0.05 and feasible_weights

    result.models = _parse_models(text)
    return result


def _extract_p_value(text: str) -> float | None:
    """Find the model tail probability (p-value).

    Most reliable source is the ``summ:`` line, which qpAdm prints as
    ``summ: <target> <ndrop> <taildev> <coeffs...>`` — the tail probability is
    the first value in (0, 1). We fall back to explicitly labelled forms.
    """
    for raw in text.splitlines():
        if raw.strip().lower().startswith("summ:"):
            for val in _floats(raw):
                if 0.0 <= val <= 1.0 and val != int(val):
                    return val

    # Labelled forms; restrict to same-line whitespace so column headers like
    # "...  tail prob\n00  ..." don't capture the next row's first token.
    patterns = [
        r"tail\s*prob[ \t]*[:=][ \t]*(" + _FLOAT + r")",
        r"\btail[ \t]*[:=][ \t]*(" + _FLOAT + r")",
        r"p-?value[ \t]*[:=]?[ \t]*(" + _FLOAT + r")",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def _parse_models(text: str) -> list[dict]:
    """Capture the rotating-model table when qpAdm is run with details.

    Rows look roughly like::

        fixed pat  wt  dof  chisq  tail  coeffs...
        00         0   1    0.34   0.56  0.41 0.59

    We keep this best-effort and skip anything that does not parse.
    """
    models: list[dict] = []
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"(fixed\s+)?pat\b", line, re.IGNORECASE) and "tail" in line.lower():
            in_table = True
            continue
        if in_table:
            if not line:
                break
            parts = line.split()
            # pattern token + at least a couple of numeric columns
            if len(parts) >= 4 and re.fullmatch(r"[01]+", parts[0]):
                nums = _floats(line)
                models.append({"pattern": parts[0], "values": nums, "raw": line})
            else:
                break
    return models


def parse_fstats_head(text: str, limit: int = 50) -> list[str]:
    """Return the first ``limit`` non-empty lines of a qpfstats file."""
    out: list[str] = []
    for raw in text.splitlines():
        if raw.strip():
            out.append(raw.rstrip())
        if len(out) >= limit:
            break
    return out
