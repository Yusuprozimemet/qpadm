"""FastAPI application: pipeline orchestration + results visualisation."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .jobs import JobManager
from .models import JobSummary, QpAdmRequest
from .parsers import parse_qpadm_output

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="qpAdm web", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

settings = get_settings()
manager = JobManager(settings)

# A reasonable default reference/outgroup set for West-Eurasian style models.
DEFAULT_REFERENCES = [
    "Mbuti.DG", "Russia_Ust_Ishim_HG.DG", "Iran_GanjDareh_N",
    "Russia_DevilsCave_N.SG", "Luxembourg_Loschbour.DG", "Karitiana.DG",
    "Ami.DG", "Russia_Kostenki14.SG",
]
DEFAULT_SOURCES = [
    "Iran_GanjDareh_N", "Russia_MLBA_Sintashta", "Turkey_N",
]


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "env": settings.environment_report(),
            "default_sources": "\n".join(DEFAULT_SOURCES),
            "default_references": "\n".join(DEFAULT_REFERENCES),
        },
    )


@app.get("/api/environment")
def environment():
    return settings.environment_report()


def _parse_pop_list(text: str) -> list[str]:
    return [line.strip() for line in text.replace(",", "\n").splitlines() if line.strip()]


@app.post("/api/run")
async def run(
    genome: UploadFile,
    sample_label: str = Form("Sample"),
    sources: str = Form(""),
    references: str = Form(""),
    allsnps: bool = Form(True),
):
    src = _parse_pop_list(sources)
    ref = _parse_pop_list(references)
    if not src:
        raise HTTPException(400, "At least one source population is required.")
    if not ref:
        raise HTTPException(400, "At least one reference population is required.")

    label = sample_label.strip() or "Sample"
    req = QpAdmRequest(
        sample_label=label, target=label, sources=src, references=ref, allsnps=allsnps
    )
    data = await genome.read()
    if not data:
        raise HTTPException(400, "Uploaded genome file is empty.")

    job = manager.submit(data, req)
    return {"job_id": job.id}


@app.get("/api/jobs")
def jobs():
    return [
        JobSummary(
            id=j.id, status=j.status, created_at=j.created_at, label=j.label,
            step=j.step, progress=j.progress, error=j.error,
        ).model_dump()
        for j in manager.list()
    ]


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id.")
    payload = JobSummary(
        id=job.id, status=job.status, created_at=job.created_at, label=job.label,
        step=job.step, progress=job.progress, error=job.error,
    ).model_dump()
    if job.result is not None:
        payload["result"] = job.result.model_dump()
    return payload


@app.post("/api/parse")
async def parse_uploaded(logfile: UploadFile):
    """Visualise an existing qpAdm log without re-running the pipeline."""
    data = (await logfile.read()).decode("utf-8", errors="replace")
    if not data.strip():
        raise HTTPException(400, "Uploaded log file is empty.")
    return JSONResponse(parse_qpadm_output(data).model_dump())
