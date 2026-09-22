"""SQLite persistence — project.md section 18.2.

JSON columns keep the Pydantic models intact; the indexed columns are the ones
the UI filters and sorts on. Schema changes go through Alembic.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    select,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import STORAGE_DIR
from app.schemas.evidence import ManualEvidence, ProfileRecord
from app.schemas.jd import JDConfig
from app.schemas.result import MatchResult

Base = declarative_base()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Profile(Base):
    __tablename__ = "profiles"
    profile_id = Column(String, primary_key=True)
    file_hash = Column(String, index=True)
    file_name = Column(String)
    lane = Column(String)
    total_exp = Column(Float)
    status = Column(String, default="parsed")
    parsed_at = Column(String, default=_now)
    parser_model = Column(String)
    prompt_version = Column(String)
    retain_until = Column(String)
    data = Column(Text)


class PiiMap(Base):
    __tablename__ = "pii_map"
    profile_id = Column(String, primary_key=True)
    data = Column(Text)


class ManualEvidenceRow(Base):
    __tablename__ = "manual_evidence"
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String, index=True)
    skill = Column(String)
    created_at = Column(String, default=_now)
    data = Column(Text)


class JD(Base):
    __tablename__ = "jds"
    jd_id = Column(String, primary_key=True)
    title = Column(String)
    source_type = Column(String)
    text_hash = Column(String, index=True)
    text = Column(Text)
    created_at = Column(String, default=_now)


class JDConfigRow(Base):
    __tablename__ = "jd_configs"
    jd_id = Column(String, primary_key=True)
    version = Column(Integer, primary_key=True)
    ai_suggestion = Column(Text)
    final = Column(Text)
    confirmed_at = Column(String, default=_now)


class MatchRun(Base):
    __tablename__ = "match_runs"
    run_id = Column(String, primary_key=True)
    jd_id = Column(String, index=True)
    jd_version = Column(Integer)
    weights = Column(Text)
    weights_hash = Column(String)
    taxonomy_version = Column(String)
    equivalence_version = Column(String)
    models = Column(Text)
    created_at = Column(String, default=_now)


class MatchResultRow(Base):
    __tablename__ = "match_results"
    run_id = Column(String, primary_key=True)
    profile_id = Column(String, primary_key=True)
    match_score = Column(Float, index=True)
    verdict = Column(String, index=True)
    confidence = Column(Integer)
    data = Column(Text)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, index=True)
    profile_id = Column(String, index=True)
    action = Column(String)
    new_verdict = Column(String)
    note = Column(Text)
    reviewer = Column(String)
    at = Column(String, default=_now)


class SkillEquivalence(Base):
    __tablename__ = "skill_equivalence"
    skill_a = Column(String, primary_key=True)
    skill_b = Column(String, primary_key=True)
    relation = Column(String)
    factor = Column(Float)
    source = Column(String)
    review_status = Column(String, default="pending")
    prompt_version = Column(String)


class LLMCache(Base):
    __tablename__ = "llm_cache"
    key = Column(String, primary_key=True)
    response = Column(Text)
    created_at = Column(String, default=_now)


class Job(Base):
    __tablename__ = "jobs"
    job_id = Column(String, primary_key=True)
    type = Column(String)
    status = Column(String, default="queued")
    progress = Column(Float, default=0.0)
    total = Column(Integer, default=0)
    done = Column(Integer, default=0)
    message = Column(String, default="")
    error = Column(Text)
    created_at = Column(String, default=_now)


class Deletion(Base):
    __tablename__ = "deletions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String)
    deleted_at = Column(String, default=_now)
    reason = Column(String)
    actor = Column(String)


class Store:
    """Thin repository over the tables above."""

    def __init__(self, url: str | None = None):
        if url is None:
            path = STORAGE_DIR / "db" / "pme.sqlite"
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{path}"
        self.engine = create_engine(url, future=True)
        Base.metadata.create_all(self.engine)
        self._session = sessionmaker(self.engine, expire_on_commit=False, future=True)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- profiles ----------------------------------------------------------

    def save_profile(
        self,
        profile: ProfileRecord,
        pii: dict[str, str] | None = None,
        model: str = "",
        prompt_version: str = "",
        retain_until: str | None = None,
    ) -> None:
        with self.session() as session:
            session.merge(
                Profile(
                    profile_id=profile.profile_id,
                    file_hash=profile.file_hash,
                    file_name=profile.file_name,
                    lane=profile.lane,
                    total_exp=profile.total_experience_years,
                    status=profile.status,
                    parsed_at=_now(),
                    parser_model=model,
                    prompt_version=prompt_version,
                    retain_until=retain_until,
                    data=profile.model_dump_json(),
                )
            )
            if pii:
                session.merge(PiiMap(profile_id=profile.profile_id, data=json.dumps(pii)))

    def load_profiles(self, include_excluded: bool = False) -> list[ProfileRecord]:
        with self.session() as session:
            rows = session.scalars(select(Profile)).all()
        out = [ProfileRecord.model_validate_json(r.data) for r in rows if r.data]
        if not include_excluded:
            out = [p for p in out if p.status != "excluded"]
        return out

    def load_profile(self, profile_id: str) -> ProfileRecord | None:
        with self.session() as session:
            row = session.get(Profile, profile_id)
        return ProfileRecord.model_validate_json(row.data) if row and row.data else None

    def known_hashes(self) -> dict[str, str]:
        with self.session() as session:
            rows = session.scalars(select(Profile)).all()
        return {r.file_hash: r.profile_id for r in rows if r.file_hash}

    def pii_for(self, profile_id: str) -> dict[str, str]:
        with self.session() as session:
            row = session.get(PiiMap, profile_id)
        return json.loads(row.data) if row and row.data else {}

    def delete_profile(self, profile_id: str, reason: str = "", actor: str = "") -> None:
        """Purge everything about a candidate — project.md 20.4."""
        with self.session() as session:
            session.execute(delete(Profile).where(Profile.profile_id == profile_id))
            session.execute(delete(PiiMap).where(PiiMap.profile_id == profile_id))
            session.execute(
                delete(ManualEvidenceRow).where(ManualEvidenceRow.profile_id == profile_id)
            )
            session.add(Deletion(profile_id=profile_id, reason=reason, actor=actor))

    # -- manual evidence ---------------------------------------------------

    def add_manual_evidence(self, entry: ManualEvidence) -> None:
        with self.session() as session:
            session.add(
                ManualEvidenceRow(
                    profile_id=entry.profile_id,
                    skill=entry.skill,
                    data=entry.model_dump_json(),
                )
            )

    def manual_evidence_for(self, profile_id: str) -> list[ManualEvidence]:
        with self.session() as session:
            rows = session.scalars(
                select(ManualEvidenceRow).where(ManualEvidenceRow.profile_id == profile_id)
            ).all()
        return [ManualEvidence.model_validate_json(r.data) for r in rows if r.data]

    # -- JDs ---------------------------------------------------------------

    def save_jd(
        self, jd_id: str, title: str, text: str, text_hash: str, source_type: str = "text"
    ) -> None:
        with self.session() as session:
            session.merge(
                JD(
                    jd_id=jd_id,
                    title=title,
                    text=text,
                    text_hash=text_hash,
                    source_type=source_type,
                )
            )

    def list_jds(self) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(select(JD)).all()
        return [
            {"jd_id": r.jd_id, "title": r.title, "created_at": r.created_at, "text": r.text}
            for r in rows
        ]

    def save_jd_config(self, config: JDConfig, ai_suggestion: JDConfig | None = None) -> None:
        with self.session() as session:
            session.merge(
                JDConfigRow(
                    jd_id=config.jd_id,
                    version=config.version,
                    ai_suggestion=(ai_suggestion or config).model_dump_json(),
                    final=config.model_dump_json(),
                    confirmed_at=_now(),
                )
            )

    def load_jd_config(self, jd_id: str, version: int | None = None) -> JDConfig | None:
        with self.session() as session:
            query = select(JDConfigRow).where(JDConfigRow.jd_id == jd_id)
            rows = session.scalars(query).all()
        if not rows:
            return None
        row = (
            max(rows, key=lambda r: r.version)
            if version is None
            else next((r for r in rows if r.version == version), None)
        )
        return JDConfig.model_validate_json(row.final) if row else None

    def next_version(self, jd_id: str) -> int:
        with self.session() as session:
            rows = session.scalars(select(JDConfigRow).where(JDConfigRow.jd_id == jd_id)).all()
        return max((r.version for r in rows), default=0) + 1

    # -- runs --------------------------------------------------------------

    def save_run(self, run, jd: JDConfig, weights, models: dict[str, str]) -> None:
        first = run.results[0] if run.results else None
        with self.session() as session:
            session.merge(
                MatchRun(
                    run_id=run.run_id,
                    jd_id=jd.jd_id,
                    jd_version=jd.version,
                    weights=json.dumps({d: weights.weight_of(d) for d in weights.dimensions}),
                    weights_hash=first.weights_hash if first else "",
                    taxonomy_version=first.taxonomy_version if first else "",
                    equivalence_version=first.equivalence_version if first else "",
                    models=json.dumps(models),
                )
            )
            for result in run.results:
                session.merge(
                    MatchResultRow(
                        run_id=run.run_id,
                        profile_id=result.profile_id,
                        match_score=result.match_score,
                        verdict=result.verdict,
                        confidence=result.analysis_confidence,
                        data=result.model_dump_json(),
                    )
                )

    def load_results(self, run_id: str) -> list[MatchResult]:
        with self.session() as session:
            rows = session.scalars(
                select(MatchResultRow).where(MatchResultRow.run_id == run_id)
            ).all()
        results = [MatchResult.model_validate_json(r.data) for r in rows if r.data]
        results.sort(key=lambda r: -r.match_score)
        return results

    def list_runs(self) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(select(MatchRun)).all()
        return [
            {
                "run_id": r.run_id,
                "jd_id": r.jd_id,
                "jd_version": r.jd_version,
                "created_at": r.created_at,
            }
            for r in sorted(rows, key=lambda r: r.created_at or "", reverse=True)
        ]

    # -- review ------------------------------------------------------------

    def add_review_action(
        self,
        run_id: str,
        profile_id: str,
        action: str,
        new_verdict: str = "",
        note: str = "",
        reviewer: str = "",
    ) -> None:
        with self.session() as session:
            session.add(
                ReviewAction(
                    run_id=run_id,
                    profile_id=profile_id,
                    action=action,
                    new_verdict=new_verdict,
                    note=note,
                    reviewer=reviewer,
                )
            )

    def review_actions(self, run_id: str) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(select(ReviewAction).where(ReviewAction.run_id == run_id)).all()
        return [
            {
                "profile_id": r.profile_id,
                "action": r.action,
                "new_verdict": r.new_verdict,
                "note": r.note,
                "reviewer": r.reviewer,
                "at": r.at,
            }
            for r in rows
        ]

    # -- equivalence review ------------------------------------------------

    def save_equivalence(
        self,
        a: str,
        b: str,
        relation: str,
        factor: float,
        source: str = "llm",
        status: str = "pending",
        prompt_version: str = "",
    ) -> None:
        with self.session() as session:
            session.merge(
                SkillEquivalence(
                    skill_a=a,
                    skill_b=b,
                    relation=relation,
                    factor=factor,
                    source=source,
                    review_status=status,
                    prompt_version=prompt_version,
                )
            )

    def equivalences(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(select(SkillEquivalence)).all()
        out = [
            {
                "skill_a": r.skill_a,
                "skill_b": r.skill_b,
                "relation": r.relation,
                "factor": r.factor,
                "source": r.source,
                "review_status": r.review_status,
            }
            for r in rows
        ]
        return [r for r in out if status is None or r["review_status"] == status]

    # -- jobs --------------------------------------------------------------

    def upsert_job(self, job_id: str, **fields: Any) -> None:
        with self.session() as session:
            job = session.get(Job, job_id) or Job(job_id=job_id)
            for key, value in fields.items():
                setattr(job, key, value)
            session.merge(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return None
            return {
                "job_id": job.job_id,
                "type": job.type,
                "status": job.status,
                "progress": job.progress,
                "total": job.total,
                "done": job.done,
                "message": job.message,
                "error": job.error,
            }
