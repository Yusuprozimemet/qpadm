"""A small in-memory background-job manager.

qpAdm runs take minutes, so the HTTP request that starts a run returns
immediately with a job id; the work happens on a worker thread and the UI polls
for status. State is in-memory (single process) which is plenty for a personal
analysis tool.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .models import QpAdmRequest, QpAdmResult
from .pipeline import PipelineError, run_pipeline


@dataclass
class Job:
    id: str
    label: str
    status: str = "queued"  # queued | running | done | error
    step: str | None = None
    progress: int = 0
    created_at: float = field(default_factory=time.time)
    error: str | None = None
    result: QpAdmResult | None = None
    dir: Path | None = None


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def submit(self, genome_bytes: bytes, req: QpAdmRequest) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.settings.work_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        genome_path = job_dir / "genome.txt"
        genome_path.write_bytes(genome_bytes)

        job = Job(id=job_id, label=req.sample_label, dir=job_dir)
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run, args=(job, genome_path, req), daemon=True
        )
        thread.start()
        return job

    def _run(self, job: Job, genome_path: Path, req: QpAdmRequest) -> None:
        def progress(step: str, pct: int) -> None:
            with self._lock:
                job.step = step
                job.progress = pct

        with self._lock:
            job.status = "running"
        try:
            result = run_pipeline(
                genome_path, req, self.settings, job.dir, progress=progress
            )
            with self._lock:
                job.result = result
                job.status = "done"
                job.step = "done"
                job.progress = 100
        except PipelineError as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                job.status = "error"
                job.error = f"unexpected error: {exc}"
