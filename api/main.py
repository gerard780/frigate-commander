"""
Frigate Commander Web API

FastAPI application with REST endpoints and WebSocket support.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import files, jobs, worker
from .jobs import JOBS_DIR
from .models import (
    Config,
    FileInfo,
    Job,
    JobCreate,
    JobProgress,
    JobStatus,
    JobSummary,
    JobType,
    Preset,
    PresetCreate,
    PresetUpdate,
)


# Configuration
BASE_DIR = Path(__file__).parent.parent
PRESETS_FILE = BASE_DIR / "jobs" / "presets.json"
CONFIG_FILE = BASE_DIR / "jobs" / "config.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: ensure directories exist
    jobs.ensure_dirs()

    # Check for interrupted jobs (from previous run) and mark them failed
    for job in jobs.get_running_jobs():
        jobs.update_job_status(
            job.id,
            JobStatus.FAILED,
            error="Server restarted while job was running",
        )

    yield

    # Shutdown: cancel all running jobs
    for job_id in worker.get_running_job_ids():
        try:
            await worker.cancel_job(job_id)
        except Exception:
            pass


app = FastAPI(
    title="Frigate Commander API",
    description="Web API for managing Frigate montage and timelapse jobs",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Jobs Endpoints
# ============================================================================

@app.post("/api/jobs", response_model=Job)
async def create_job(job_create: JobCreate):
    """Create and start a new job."""
    job = jobs.create_job(job_create)

    # Start the job in background
    worker.start_job(job.id)

    return job


@app.get("/api/jobs", response_model=List[JobSummary])
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    type: Optional[str] = Query(None, description="Filter by job type"),
    camera: Optional[str] = Query(None, description="Filter by camera"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List all jobs with optional filters."""
    status_enum = None
    if status:
        try:
            status_enum = JobStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    return jobs.list_jobs(
        status=status_enum,
        job_type=type,
        camera=camera,
        limit=limit,
        offset=offset,
    )


@app.get("/api/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str):
    """Get job details."""
    job = jobs.load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, cancel: bool = Query(True)):
    """Delete a job. If running and cancel=true, cancels first."""
    job = jobs.load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Cancel if running
    if job.status == JobStatus.RUNNING and cancel:
        await worker.cancel_job(job_id)
        # Give it a moment to clean up
        await asyncio.sleep(0.5)

    if not jobs.delete_job(job_id):
        raise HTTPException(500, "Failed to delete job")

    return {"status": "deleted"}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job."""
    job = jobs.load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(400, f"Cannot cancel job with status: {job.status}")

    await worker.cancel_job(job_id)
    return {"status": "cancelled"}


@app.post("/api/jobs/{job_id}/retry", response_model=Job)
async def retry_job(job_id: str):
    """Retry a failed or cancelled job."""
    old_job = jobs.load_job(job_id)
    if not old_job:
        raise HTTPException(404, "Job not found")

    if old_job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(400, f"Cannot retry job with status: {old_job.status}")

    # Create a new job with same parameters
    job_create = JobCreate(
        type=old_job.type,
        camera=old_job.camera,
        arguments=old_job.arguments,
    )
    new_job = jobs.create_job(job_create)
    worker.start_job(new_job.id)

    return new_job


@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, tail: int = Query(200, ge=1, le=10000)):
    """Get job log output."""
    job = jobs.load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    logs = jobs.get_job_logs(job_id, tail=tail)
    return {"job_id": job_id, "logs": logs or ""}


@app.get("/api/jobs/{job_id}/clone")
async def get_clone_data(job_id: str):
    """Get job data for cloning (creating a new job based on this one)."""
    job = jobs.load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "type": job.type,
        "camera": job.camera,
        "arguments": job.arguments,
    }


# ============================================================================
# Files Endpoints
# ============================================================================

@app.get("/api/files", response_model=List[FileInfo])
async def list_files(
    sort: str = Query("modified", regex="^(name|modified|size)$"),
    desc: bool = Query(True),
    videos_only: bool = Query(False),
):
    """List output files."""
    extensions = files.VIDEO_EXTENSIONS if videos_only else None
    return files.list_files(sort_by=sort, descending=desc, extensions=extensions)


@app.get("/api/files/{filename}")
async def get_file(filename: str, download: bool = Query(False)):
    """Get or download a file."""
    path = files.get_file_path(filename)
    if not path:
        raise HTTPException(404, "File not found")

    mime_type = files.get_mime_type(filename)

    if download:
        return FileResponse(
            path,
            media_type=mime_type,
            filename=filename,
        )
    else:
        return FileResponse(
            path,
            media_type=mime_type,
        )


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """Delete a file and its associated files."""
    if not files.delete_file(filename):
        raise HTTPException(404, "File not found or could not be deleted")
    return {"status": "deleted"}


@app.get("/api/files/{filename}/thumbnail")
async def get_file_thumbnail(filename: str):
    """Get thumbnail for a video file."""
    import subprocess
    import tempfile

    path = files.get_file_path(filename)
    if not path:
        raise HTTPException(404, "File not found")

    # Only generate thumbnails for videos
    if not files.get_file(filename).is_video:
        raise HTTPException(400, "Not a video file")

    # Check for cached thumbnail
    thumb_dir = JOBS_DIR / "thumbnails"
    thumb_dir.mkdir(exist_ok=True)
    thumb_path = thumb_dir / f"{path.stem}.jpg"

    if not thumb_path.exists():
        # Generate thumbnail using ffmpeg (grab frame at 10% into video)
        try:
            # First, get video duration
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path)
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            duration = float(result.stdout.strip()) if result.stdout.strip() else 10

            # Seek to 10% of video duration for more representative thumbnail
            seek_time = min(duration * 0.1, 30)  # Max 30 seconds in

            cmd = [
                "ffmpeg", "-y", "-ss", str(seek_time),
                "-i", str(path),
                "-vframes", "1",
                "-vf", "scale=320:-1",
                "-q:v", "5",
                str(thumb_path)
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
        except Exception:
            raise HTTPException(500, "Failed to generate thumbnail")

    if not thumb_path.exists():
        raise HTTPException(500, "Thumbnail generation failed")

    return FileResponse(thumb_path, media_type="image/jpeg")


@app.get("/api/files/{filename}/info", response_model=FileInfo)
async def get_file_info(filename: str):
    """Get file information."""
    info = files.get_file(filename)
    if not info:
        raise HTTPException(404, "File not found")
    return info


# ============================================================================
# Config Endpoints
# ============================================================================

@app.get("/api/cameras")
async def list_cameras():
    """List cameras from Frigate API, with fallback to past jobs."""
    import httpx

    # Try to get config to find Frigate URL
    config = Config()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            config = Config(**data)
        except Exception:
            pass

    frigate_cameras = []
    frigate_error = None

    # Try to fetch from Frigate API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.default_base_url}/api/config")
            if response.status_code == 200:
                frigate_config = response.json()
                if "cameras" in frigate_config:
                    frigate_cameras = sorted(frigate_config["cameras"].keys())
    except Exception as e:
        frigate_error = str(e)

    # Get cameras from past jobs as fallback/supplement
    job_list = jobs.list_jobs(limit=1000)
    job_cameras = sorted(set(j.camera for j in job_list))

    # Merge and deduplicate
    all_cameras = sorted(set(frigate_cameras + job_cameras))

    return {
        "cameras": all_cameras,
        "from_frigate": frigate_cameras,
        "from_jobs": job_cameras,
        "frigate_error": frigate_error,
    }


@app.get("/api/config", response_model=Config)
async def get_config():
    """Get application configuration."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return Config(**data)
        except Exception:
            pass
    return Config()


@app.put("/api/config", response_model=Config)
async def update_config(config: Config):
    """Update application configuration."""
    jobs.ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.model_dump(), f, indent=2)
    return config


# ============================================================================
# Presets Endpoints
# ============================================================================

def load_presets() -> List[Preset]:
    """Load presets from file."""
    if not PRESETS_FILE.exists():
        return []
    try:
        with open(PRESETS_FILE, "r") as f:
            data = json.load(f)
        return [Preset(**p) for p in data]
    except Exception:
        return []


def save_presets(presets: List[Preset]) -> None:
    """Save presets to file."""
    jobs.ensure_dirs()
    with open(PRESETS_FILE, "w") as f:
        json.dump([p.model_dump(mode="json") for p in presets], f, indent=2, default=str)


@app.get("/api/presets", response_model=List[Preset])
async def list_presets():
    """List saved presets."""
    return load_presets()


@app.post("/api/presets", response_model=Preset)
async def create_preset(preset_create: PresetCreate):
    """Create a new preset."""
    preset = Preset(
        id=jobs.generate_job_id(),
        name=preset_create.name,
        type=preset_create.type,
        camera=preset_create.camera,
        arguments=preset_create.arguments,
        created_at=datetime.utcnow(),
    )
    presets = load_presets()
    presets.append(preset)
    save_presets(presets)
    return preset


@app.delete("/api/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a preset."""
    presets = load_presets()
    presets = [p for p in presets if p.id != preset_id]
    save_presets(presets)
    return {"status": "deleted"}


@app.put("/api/presets/{preset_id}", response_model=Preset)
async def update_preset(preset_id: str, preset_update: PresetUpdate):
    """Update an existing preset."""
    presets = load_presets()

    # Find the preset to update
    preset_index = None
    for i, p in enumerate(presets):
        if p.id == preset_id:
            preset_index = i
            break

    if preset_index is None:
        raise HTTPException(404, "Preset not found")

    # Update fields that were provided
    existing = presets[preset_index]
    updated = Preset(
        id=existing.id,
        name=preset_update.name if preset_update.name is not None else existing.name,
        type=preset_update.type if preset_update.type is not None else existing.type,
        camera=preset_update.camera if preset_update.camera is not None else existing.camera,
        arguments=preset_update.arguments if preset_update.arguments is not None else existing.arguments,
        created_at=existing.created_at,
    )

    presets[preset_index] = updated
    save_presets(presets)
    return updated


# ============================================================================
# WebSocket Endpoint
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections for job progress updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)

    def disconnect(self, job_id: str, websocket: WebSocket):
        if job_id in self.active_connections:
            try:
                self.active_connections[job_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

    async def send_job_update(self, job: Job):
        if job.id not in self.active_connections:
            return
        message = job.model_dump_json()
        for connection in self.active_connections[job.id]:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/api/ws/jobs/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job progress updates."""
    job = jobs.load_job(job_id)
    if not job:
        await websocket.close(code=4004)
        return

    await manager.connect(job_id, websocket)

    # Send initial state
    try:
        await websocket.send_text(job.model_dump_json())
    except Exception:
        manager.disconnect(job_id, websocket)
        return

    # Register callback for progress updates
    async def on_progress(updated_job: Job):
        await manager.send_job_update(updated_job)

    # We need a sync wrapper for the async callback
    loop = asyncio.get_event_loop()

    def sync_callback(updated_job: Job):
        asyncio.run_coroutine_threadsafe(on_progress(updated_job), loop)

    worker.register_progress_callback(job_id, sync_callback)

    try:
        while True:
            # Keep connection alive, handle any incoming messages
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Handle ping/pong or commands
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_text('{"type":"heartbeat"}')
                except Exception:
                    break

            # Check if job is complete
            job = jobs.load_job(job_id)
            if job and job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                # Send final state and close
                await websocket.send_text(job.model_dump_json())
                break

    except WebSocketDisconnect:
        pass
    finally:
        worker.unregister_progress_callback(job_id, sync_callback)
        manager.disconnect(job_id, websocket)


# ============================================================================
# YouTube Upload Endpoints
# ============================================================================

YOUTUBE_TOKEN_DIR = BASE_DIR / "tokens"
YOUTUBE_TOKEN_FILE = YOUTUBE_TOKEN_DIR / "joselyn85.json"  # Default token
YOUTUBE_SECRETS_FILE = BASE_DIR / "client_secret.json"


@app.get("/api/youtube/status")
async def youtube_status():
    """Check if YouTube upload is configured."""
    has_secrets = YOUTUBE_SECRETS_FILE.exists()
    has_token = YOUTUBE_TOKEN_FILE.exists()

    return {
        "configured": has_secrets,
        "authenticated": has_token,
        "setup_needed": not has_secrets,
        "auth_needed": has_secrets and not has_token,
    }


@app.get("/api/youtube/accounts")
async def list_youtube_accounts():
    """List available YouTube accounts (token files)."""
    accounts = []
    if YOUTUBE_TOKEN_DIR.exists():
        for token_file in YOUTUBE_TOKEN_DIR.glob("*.json"):
            # Extract account name from filename (without .json extension)
            # Skip backup/previous token files
            if "-prev" in token_file.stem:
                continue
            account_name = token_file.stem
            accounts.append({
                "name": account_name,
                "file": token_file.name,
            })
    return {
        "accounts": sorted(accounts, key=lambda x: x["name"]),
        "default": "joselyn85",
    }


@app.post("/api/youtube/upload")
async def youtube_upload(
    filename: str = Query(..., description="File to upload (from Files)"),
    title: str = Query(..., description="Video title"),
    description: str = Query("", description="Video description"),
    tags: str = Query("", description="Comma-separated tags"),
    category: str = Query("pets", description="Video category"),
    privacy: str = Query("unlisted", description="Privacy: public, unlisted, private"),
    account: str = Query("joselyn85", description="YouTube account name (token filename without .json)"),
):
    """Upload a file to YouTube."""
    import subprocess

    # Verify file exists
    file_path = files.get_file_path(filename)
    if not file_path:
        raise HTTPException(404, "File not found")

    # Check YouTube is configured
    if not YOUTUBE_SECRETS_FILE.exists():
        raise HTTPException(400, "YouTube not configured. Download client_secrets.json from Google Cloud Console.")

    # Resolve token file for the specified account
    token_file = YOUTUBE_TOKEN_DIR / f"{account}.json"
    if not token_file.exists():
        raise HTTPException(400, f"YouTube account '{account}' not found. No token file at {token_file}")

    # Build upload command
    cmd = [
        "python3", str(BASE_DIR / "youtube_upload.py"),
        "--file", str(file_path),
        "--title", title,
        "--description", description,
        "--category", category,
        "--privacy", privacy,
        "--token-file", str(token_file),
    ]
    if tags:
        cmd += ["--tags", tags]

    # Run upload (this may take a while for large files)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        if result.returncode == 0:
            # Parse video URL from output
            output = result.stdout
            url_line = [l for l in output.split("\n") if "youtube.com/watch" in l]
            video_url = url_line[0].split()[-1] if url_line else None

            return {
                "status": "success",
                "message": "Video uploaded successfully",
                "url": video_url,
                "output": output,
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Upload failed",
                    "error": result.stderr or result.stdout,
                },
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Upload timed out")
    except Exception as e:
        raise HTTPException(500, f"Upload error: {str(e)}")


# ============================================================================
# Static Files (Frontend)
# ============================================================================

# Serve frontend static files if they exist
FRONTEND_DIR = BASE_DIR / "web" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "running_jobs": len(worker.get_running_job_ids()),
    }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
