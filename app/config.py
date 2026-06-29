"""Application configuration.

All paths to external tools and the reference dataset are configurable so the
app is not tied to the hard-coded ``/content/...`` Colab layout of the old
notebook. Values are read from environment variables or a local ``.env`` file.
"""
from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admixtools_bin: str = ""
    plink_bin: str = ""
    reference_dir: str = ""
    reference_prefix: str = "v54.1.p1_1240K_public"
    work_dir: str = "./workdir"

    # ---- derived helpers -------------------------------------------------

    def tool_path(self, name: str) -> str | None:
        """Resolve an AdmixTools binary by name.

        Looks inside ``admixtools_bin`` first, then falls back to PATH.
        Returns ``None`` if it cannot be found.
        """
        if self.admixtools_bin:
            candidate = Path(self.admixtools_bin) / name
            if candidate.exists():
                return str(candidate)
            # On Windows the same binary may carry an .exe suffix.
            candidate_exe = candidate.with_suffix(".exe")
            if candidate_exe.exists():
                return str(candidate_exe)
        return shutil.which(name)

    @property
    def plink_path(self) -> str | None:
        if self.plink_bin and Path(self.plink_bin).exists():
            return self.plink_bin
        return shutil.which(self.plink_bin or "plink")

    @property
    def work_path(self) -> Path:
        p = Path(self.work_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def reference_trio(self) -> dict[str, Path]:
        base = Path(self.reference_dir) / self.reference_prefix
        return {
            "geno": base.with_suffix(".geno"),
            "snp": base.with_suffix(".snp"),
            "ind": base.with_suffix(".ind"),
        }

    def environment_report(self) -> dict[str, object]:
        """Inspect the host for everything the pipeline needs.

        Returned to the UI so the user can see exactly what is missing rather
        than hitting an opaque subprocess error mid-run.
        """
        tools = {name: self.tool_path(name) for name in ("convertf", "mergeit", "qpfstats", "qpAdm")}
        tools["plink"] = self.plink_path

        ref = self.reference_trio()
        ref_status = {ext: (str(p) if p.exists() else None) for ext, p in ref.items()}
        reference_ready = all(ref_status.values())

        return {
            "tools": tools,
            "tools_ready": all(tools.values()),
            "reference": ref_status,
            "reference_ready": reference_ready,
            "reference_dir": self.reference_dir or "(unset)",
            "work_dir": str(self.work_path),
            "pipeline_ready": all(tools.values()) and reference_ready,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
