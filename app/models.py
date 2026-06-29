"""Pydantic request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class QpAdmRequest(BaseModel):
    """Configuration for a single qpAdm model run."""

    sample_label: str = Field(default="Sample", description="Name to give the uploaded individual.")
    target: str = Field(description="Target population (the uploaded sample, by default its label).")
    sources: list[str] = Field(min_length=1, description="Left/source populations.")
    references: list[str] = Field(min_length=1, description="Right/reference (outgroup) populations.")
    allsnps: bool = True


class JobSummary(BaseModel):
    id: str
    status: str
    created_at: float
    label: str
    step: str | None = None
    progress: int = 0
    error: str | None = None


class Coefficient(BaseModel):
    source: str
    weight: float
    std_error: float | None = None


class QpAdmResult(BaseModel):
    target: str | None = None
    sources: list[str] = []
    references: list[str] = []
    coefficients: list[Coefficient] = []
    p_value: float | None = None
    feasible: bool | None = None
    models: list[dict] = []
    raw_output: str = ""
