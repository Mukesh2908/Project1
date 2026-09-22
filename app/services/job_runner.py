"""Background ingestion — project.md 17.2.

Streamlit re-runs its script on every interaction, so long work cannot live on
the render path. Ingestion runs on a worker thread and reports progress through
the ``jobs`` table, which the UI polls with a fragment.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from pathlib import Path

from app.ai.provider import AIProvider
from app.models.store import Store
from app.services.profile_analyzer import ingest_file


def start_ingest(
    store: Store,
    paths: list[Path],
    provider: AIProvider,
    model: str,
    real_data: bool = False,
) -> str:
    """Kick off ingestion and return a job id to poll."""
    job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
    store.upsert_job(
        job_id,
        type="ingest",
        status="running",
        total=len(paths),
        done=0,
        progress=0.0,
        message="Starting",
    )

    def worker() -> None:
        done = 0
        try:
            for path in paths:
                store.upsert_job(job_id, message=f"Parsing {path.name}")
                try:
                    result = ingest_file(
                        path,
                        provider,
                        model=model,
                        known_hashes=store.known_hashes(),
                        real_data=real_data,
                    )
                    if not result.skipped:
                        store.save_profile(
                            result.profile,
                            result.pii_map,
                            model=model,
                            prompt_version="profile_parser_v1",
                        )
                except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
                    store.upsert_job(job_id, message=f"{path.name}: {exc}")
                done += 1
                store.upsert_job(job_id, done=done, progress=done / max(1, len(paths)))
            store.upsert_job(job_id, status="done", message="Complete", progress=1.0)
        except Exception:  # noqa: BLE001
            store.upsert_job(job_id, status="failed", error=traceback.format_exc())

    threading.Thread(target=worker, daemon=True, name=f"ingest-{job_id}").start()
    return job_id
