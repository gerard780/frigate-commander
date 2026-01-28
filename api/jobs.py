"""
Job management: CRUD operations and JSON file storage.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from .models import Job, JobCreate, JobProgress, JobStatus, JobSummary


# Default paths
JOBS_DIR = Path(__file__).parent.parent / "jobs"
MONTAGES_DIR = Path(__file__).parent.parent / "montages"


def ensure_dirs():
    """Ensure required directories exist."""
    JOBS_DIR.mkdir(exist_ok=True)
    MONTAGES_DIR.mkdir(exist_ok=True)


def job_path(job_id: str) -> Path:
    """Get path to job JSON file."""
    return JOBS_DIR / f"{job_id}.json"


def log_path(job_id: str) -> Path:
    """Get path to job log file."""
    return JOBS_DIR / f"{job_id}.log"


def generate_job_id() -> str:
    """Generate a short unique job ID."""
    return uuid4().hex[:12]


def create_job(job_create: JobCreate) -> Job:
    """Create a new job and save to disk."""
    ensure_dirs()

    job_id = generate_job_id()
    now = datetime.utcnow()

    job = Job(
        id=job_id,
        type=job_create.type,
        status=JobStatus.PENDING,
        camera=job_create.camera,
        created_at=now,
        arguments=job_create.arguments,
        log_file=str(log_path(job_id)),
    )

    save_job(job)
    return job


def save_job(job: Job) -> None:
    """Save job to JSON file."""
    ensure_dirs()
    path = job_path(job.id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job.model_dump(mode="json"), f, indent=2, default=str)


def load_job(job_id: str) -> Optional[Job]:
    """Load job from JSON file."""
    path = job_path(job_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Job(**data)
    except Exception:
        return None


def list_jobs(
    status: Optional[JobStatus] = None,
    job_type: Optional[str] = None,
    camera: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[JobSummary]:
    """List jobs with optional filters."""
    ensure_dirs()

    jobs: List[Job] = []
    for path in JOBS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            job = Job(**data)

            # Apply filters
            if status and job.status != status:
                continue
            if job_type and job.type.value != job_type:
                continue
            if camera and job.camera != camera:
                continue

            jobs.append(job)
        except Exception:
            continue

    # Sort by created_at descending (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)

    # Apply pagination
    paginated = jobs[offset:offset + limit]

    # Convert to summaries
    return [
        JobSummary(
            id=j.id,
            type=j.type,
            status=j.status,
            camera=j.camera,
            created_at=j.created_at,
            started_at=j.started_at,
            completed_at=j.completed_at,
            progress=j.progress,
            output_file=j.output_file,
            error=j.error,
        )
        for j in paginated
    ]


def delete_job(job_id: str) -> bool:
    """Delete job and its log file."""
    path = job_path(job_id)
    log = log_path(job_id)

    deleted = False
    if path.exists():
        path.unlink()
        deleted = True
    if log.exists():
        log.unlink()

    return deleted


def update_job_status(job_id: str, status: JobStatus, error: Optional[str] = None) -> Optional[Job]:
    """Update job status."""
    job = load_job(job_id)
    if not job:
        return None

    job.status = status
    if error:
        job.error = error

    if status == JobStatus.RUNNING and not job.started_at:
        job.started_at = datetime.utcnow()
    elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        job.completed_at = datetime.utcnow()

    save_job(job)
    return job


def update_job_progress(job_id: str, progress: JobProgress) -> Optional[Job]:
    """Update job progress."""
    job = load_job(job_id)
    if not job:
        return None

    job.progress = progress
    save_job(job)
    return job


def update_job_output(job_id: str, output_file: str) -> Optional[Job]:
    """Update job output file path."""
    job = load_job(job_id)
    if not job:
        return None

    job.output_file = output_file
    save_job(job)
    return job


def update_job_pid(job_id: str, pid: int) -> Optional[Job]:
    """Update job process ID."""
    job = load_job(job_id)
    if not job:
        return None

    job.pid = pid
    save_job(job)
    return job


def get_job_logs(job_id: str, tail: int = 100) -> Optional[str]:
    """Get job log contents (last N lines)."""
    path = log_path(job_id)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if tail and len(lines) > tail:
            lines = lines[-tail:]

        return "".join(lines)
    except Exception:
        return None


def append_job_log(job_id: str, text: str) -> None:
    """Append text to job log file."""
    ensure_dirs()
    path = log_path(job_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def get_running_jobs() -> List[Job]:
    """Get all currently running jobs."""
    ensure_dirs()

    jobs: List[Job] = []
    for path in JOBS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            job = Job(**data)
            if job.status == JobStatus.RUNNING:
                jobs.append(job)
        except Exception:
            continue

    return jobs
