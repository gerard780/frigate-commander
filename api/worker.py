"""
Background job runner: executes CLI scripts and parses progress.
"""

import asyncio
import os
import re
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .jobs import (
    append_job_log,
    load_job,
    save_job,
    update_job_output,
    update_job_pid,
    update_job_progress,
    update_job_status,
)
from .models import Job, JobProgress, JobStatus, JobType


# Base directory for scripts
BASE_DIR = Path(__file__).parent.parent


# Global registry of running jobs and their callbacks
_running_jobs: Dict[str, asyncio.Task] = {}
_progress_callbacks: Dict[str, List[Callable[[Job], None]]] = {}


def register_progress_callback(job_id: str, callback: Callable[[Job], None]) -> None:
    """Register a callback to be called on job progress updates."""
    if job_id not in _progress_callbacks:
        _progress_callbacks[job_id] = []
    _progress_callbacks[job_id].append(callback)


def unregister_progress_callback(job_id: str, callback: Callable[[Job], None]) -> None:
    """Unregister a progress callback."""
    if job_id in _progress_callbacks:
        try:
            _progress_callbacks[job_id].remove(callback)
        except ValueError:
            pass
        if not _progress_callbacks[job_id]:
            del _progress_callbacks[job_id]


def _notify_progress(job: Job) -> None:
    """Notify all registered callbacks of progress update."""
    callbacks = _progress_callbacks.get(job.id, [])
    for cb in callbacks:
        try:
            cb(job)
        except Exception:
            pass


def build_montage_command(job: Job) -> List[str]:
    """Build command for montage job."""
    args = job.arguments
    cmd = ["python3", str(BASE_DIR / "frigate_montage.py")]

    cmd += ["--camera", job.camera]

    # String arguments
    for key in ["base_url", "date", "start_date", "end_date", "start_time", "end_time",
                "labels_include", "labels_exclude", "recordings_path", "source", "encoder"]:
        key_arg = key.replace("_", "-")
        if args.get(key):
            cmd += [f"--{key_arg}", str(args[key])]

    # Integer arguments
    for key in ["days", "pre_pad", "post_pad", "merge_gap", "min_segment_len", "min_motion"]:
        key_arg = key.replace("_", "-")
        if args.get(key) is not None:
            cmd += [f"--{key_arg}", str(args[key])]

    # Float arguments
    for key in ["min_score", "timelapse"]:
        key_arg = key.replace("_", "-")
        if args.get(key) is not None:
            cmd += [f"--{key_arg}", str(args[key])]

    # Boolean flags
    if args.get("dawntodusk"):
        cmd.append("--dawntodusk")
    if args.get("dusktodawn"):
        cmd.append("--dusktodawn")
    if args.get("encode"):
        cmd.append("--encode")
    if args.get("all_motion"):
        cmd.append("--all-motion")
    if args.get("progress"):
        cmd.append("--progress")

    # List arguments
    for fallback in args.get("recordings_path_fallback") or []:
        cmd += ["--recordings-path-fallback", str(fallback)]

    return cmd


def build_timelapse_command(job: Job) -> List[str]:
    """Build command for timelapse job."""
    args = job.arguments
    cmd = ["python3", str(BASE_DIR / "frigate_timelapse.py")]

    cmd += ["--camera", job.camera]

    # String arguments
    for key in ["recordings_path", "base_url", "source", "date", "start_date", "end_date", "start_time", "end_time",
                "encoder", "preset", "scale"]:
        key_arg = key.replace("_", "-")
        if args.get(key):
            cmd += [f"--{key_arg}", str(args[key])]

    # Integer arguments
    for key in ["days", "dawn_offset", "dusk_offset", "fps", "cq", "crf"]:
        key_arg = key.replace("_", "-")
        if args.get(key) is not None:
            cmd += [f"--{key_arg}", str(args[key])]

    # Float arguments
    for key in ["timelapse", "frame_sample", "sample_interval"]:
        key_arg = key.replace("_", "-")
        if args.get(key) is not None:
            cmd += [f"--{key_arg}", str(args[key])]

    # Boolean flags
    if args.get("dawntodusk"):
        cmd.append("--dawntodusk")
    if args.get("dusktodawn"):
        cmd.append("--dusktodawn")
    if args.get("cuda"):
        cmd.append("--cuda")
    if args.get("audio"):
        cmd.append("--audio")

    # List arguments
    for fallback in args.get("recordings_path_fallback") or []:
        cmd += ["--recordings-path-fallback", str(fallback)]

    return cmd


def build_motion_playlist_command(job: Job) -> List[str]:
    """Build command for motion playlist job."""
    args = job.arguments
    cmd = ["python3", str(BASE_DIR / "frigate_motion_playlist.py")]

    cmd += ["--camera", job.camera]

    # Required output file
    output_name = f"{job.camera}-motion-{job.id}.m3u"
    output_path = str(BASE_DIR / "montages" / output_name)
    cmd += ["--out", output_path]

    # String arguments
    if args.get("base_url"):
        cmd += ["--base-url", str(args["base_url"])]

    # Integer arguments
    for key in ["limit", "default_duration"]:
        key_arg = key.replace("_", "-")
        if args.get(key) is not None:
            cmd += [f"--{key_arg}", str(args[key])]

    # Float arguments
    for key in ["start", "end"]:
        if args.get(key) is not None:
            cmd += [f"--{key}", str(args[key])]

    return cmd


def build_command(job: Job) -> List[str]:
    """Build the appropriate command for a job."""
    if job.type == JobType.MONTAGE:
        return build_montage_command(job)
    elif job.type == JobType.TIMELAPSE:
        return build_timelapse_command(job)
    elif job.type == JobType.MOTION_PLAYLIST:
        return build_motion_playlist_command(job)
    else:
        raise ValueError(f"Unknown job type: {job.type}")


# Progress parsing patterns
PROGRESS_PATTERNS = [
    # "Progress: 45.0% time=00:01:23 speed=12.3x"
    re.compile(r"Progress:\s*([\d.]+)%"),
    # "Progress: 1234/5678 (success=1234)"
    re.compile(r"Progress:\s*(\d+)/(\d+)"),
    # "Extracting first frame from N files"
    re.compile(r"Extracting first frame from (\d+) files"),
    # "Encoding X.mp4..."
    re.compile(r"Encoding (.+\.mp4)"),
]


def parse_progress(line: str, current_progress: JobProgress) -> JobProgress:
    """Parse a line of output and extract progress info."""
    line = line.strip()

    # Check for percentage progress
    match = PROGRESS_PATTERNS[0].search(line)
    if match:
        pct = float(match.group(1))
        return JobProgress(
            phase=current_progress.phase or "render",
            percent=min(100.0, pct),
            message=line,
        )

    # Check for count progress (X/Y)
    match = PROGRESS_PATTERNS[1].search(line)
    if match:
        done = int(match.group(1))
        total = int(match.group(2))
        pct = (done / total * 100) if total > 0 else 0
        return JobProgress(
            phase=current_progress.phase or "process",
            percent=min(100.0, pct),
            message=line,
        )

    # Check for extraction start
    match = PROGRESS_PATTERNS[2].search(line)
    if match:
        return JobProgress(
            phase="extract",
            percent=0,
            message=line,
        )

    # Check for encoding start
    match = PROGRESS_PATTERNS[3].search(line)
    if match:
        return JobProgress(
            phase="encode",
            percent=current_progress.percent,
            message=line,
        )

    # Phase detection from keywords
    lower = line.lower()
    if "segment" in lower and ("found" in lower or "total" in lower):
        return JobProgress(phase="segments", percent=0, message=line)
    if "concat" in lower:
        return JobProgress(phase="concat", percent=0, message=line)
    if "running:" in lower or "ffmpeg" in lower:
        return JobProgress(phase="render", percent=0, message=line)
    if "done:" in lower:
        return JobProgress(phase="complete", percent=100, message=line)
    if "error" in lower or "failed" in lower:
        return JobProgress(phase="error", percent=current_progress.percent, message=line)

    # Keep current progress but update message if line is informative
    if line and not line.startswith("["):
        return JobProgress(
            phase=current_progress.phase,
            percent=current_progress.percent,
            message=line,
        )

    return current_progress


def extract_output_file(line: str) -> Optional[str]:
    """Try to extract output file path from a line."""
    # "DONE: /path/to/file.mp4"
    if line.startswith("DONE:"):
        path = line[5:].strip()
        if os.path.exists(path):
            return path

    # "Output: /path/to/file.mp4"
    if line.startswith("Output:"):
        path = line[7:].strip()
        if os.path.exists(path):
            return path

    # "Wrote N entries to /path/to/file.m3u"
    match = re.search(r"Wrote \d+ entries to (.+)$", line)
    if match:
        path = match.group(1).strip()
        if os.path.exists(path):
            return path

    return None


async def run_job(job_id: str) -> None:
    """Run a job asynchronously."""
    job = load_job(job_id)
    if not job:
        return

    # Update status to running
    job = update_job_status(job_id, JobStatus.RUNNING)
    if not job:
        return

    cmd = build_command(job)
    append_job_log(job_id, f"[{datetime.utcnow().isoformat()}] Starting job\n")
    append_job_log(job_id, f"Command: {' '.join(cmd)}\n\n")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )

        # Store PID
        if process.pid:
            update_job_pid(job_id, process.pid)

        progress = JobProgress(phase="starting", percent=0, message="Starting...")
        output_file = None

        # Read output line by line
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            text = line.decode("utf-8", errors="replace")
            append_job_log(job_id, text)

            # Parse progress
            new_progress = parse_progress(text, progress)
            if new_progress != progress:
                progress = new_progress
                job = update_job_progress(job_id, progress)
                if job:
                    _notify_progress(job)

            # Check for output file
            extracted = extract_output_file(text.strip())
            if extracted:
                output_file = extracted

        await process.wait()

        # Final status update
        if process.returncode == 0:
            if output_file:
                update_job_output(job_id, output_file)
            job = update_job_status(job_id, JobStatus.COMPLETED)
            append_job_log(job_id, f"\n[{datetime.utcnow().isoformat()}] Job completed successfully\n")
        else:
            job = update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Process exited with code {process.returncode}",
            )
            append_job_log(job_id, f"\n[{datetime.utcnow().isoformat()}] Job failed (exit code {process.returncode})\n")

    except asyncio.CancelledError:
        job = update_job_status(job_id, JobStatus.CANCELLED, error="Job was cancelled")
        append_job_log(job_id, f"\n[{datetime.utcnow().isoformat()}] Job cancelled\n")
        raise

    except Exception as e:
        job = update_job_status(job_id, JobStatus.FAILED, error=str(e))
        append_job_log(job_id, f"\n[{datetime.utcnow().isoformat()}] Job failed: {e}\n")

    finally:
        # Clean up
        if job_id in _running_jobs:
            del _running_jobs[job_id]

        # Final notification
        job = load_job(job_id)
        if job:
            _notify_progress(job)


def start_job(job_id: str) -> bool:
    """Start a job in the background. Returns True if started successfully."""
    if job_id in _running_jobs:
        return False  # Already running

    task = asyncio.create_task(run_job(job_id))
    _running_jobs[job_id] = task
    return True


async def cancel_job(job_id: str) -> bool:
    """Cancel a running job."""
    if job_id not in _running_jobs:
        # Check if it's pending and just mark cancelled
        job = load_job(job_id)
        if job and job.status == JobStatus.PENDING:
            update_job_status(job_id, JobStatus.CANCELLED, error="Cancelled before starting")
            return True
        return False

    task = _running_jobs[job_id]

    # Also try to kill the subprocess
    job = load_job(job_id)
    if job and job.pid:
        try:
            os.kill(job.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    return True


def is_job_running(job_id: str) -> bool:
    """Check if a job is currently running."""
    return job_id in _running_jobs


def get_running_job_ids() -> List[str]:
    """Get list of currently running job IDs."""
    return list(_running_jobs.keys())
