"""
Pydantic models for the Frigate Commander API.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobType(str, Enum):
    MONTAGE = "montage"
    TIMELAPSE = "timelapse"
    MOTION_PLAYLIST = "motion_playlist"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobProgress(BaseModel):
    phase: str = "pending"
    percent: float = 0.0
    message: str = ""


class MontageArguments(BaseModel):
    """Arguments for montage job."""
    base_url: str = "http://127.0.0.1:5000"
    date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    dawntodusk: bool = False
    dusktodawn: bool = False
    pre_pad: int = 5
    post_pad: int = 5
    merge_gap: int = 15
    min_segment_len: int = 2
    min_score: float = 0.0
    labels_include: Optional[str] = None
    labels_exclude: Optional[str] = None
    all_motion: bool = False
    min_motion: int = 0
    recordings_path: Optional[str] = None
    recordings_path_fallback: Optional[List[str]] = None
    source: str = "disk"
    encoder: str = "hevc_nvenc"
    timelapse: Optional[float] = None
    copy_mode: bool = True
    encode: bool = False
    progress: bool = True


class TimelapseArguments(BaseModel):
    """Arguments for timelapse job."""
    recordings_path: Optional[str] = None
    recordings_path_fallback: Optional[List[str]] = None
    date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    dawntodusk: bool = False
    dusktodawn: bool = False
    dawn_offset: int = 0
    dusk_offset: int = 0
    timelapse: float = 50.0
    frame_sample: Optional[float] = None
    sample_interval: Optional[float] = None
    fps: int = 20
    encoder: str = "hevc_nvenc"
    preset: Optional[str] = None
    cq: Optional[int] = None
    crf: Optional[int] = None
    scale: Optional[str] = None
    cuda: bool = False
    audio: bool = False


class MotionPlaylistArguments(BaseModel):
    """Arguments for motion playlist job."""
    base_url: str = "http://127.0.0.1:5000"
    limit: int = 500
    start: Optional[float] = None
    end: Optional[float] = None
    default_duration: int = 30


class JobCreate(BaseModel):
    """Request body for creating a new job."""
    type: JobType
    camera: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    """Complete job model stored in JSON."""
    id: str
    type: JobType
    status: JobStatus = JobStatus.PENDING
    camera: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: JobProgress = Field(default_factory=JobProgress)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    output_file: Optional[str] = None
    error: Optional[str] = None
    log_file: Optional[str] = None
    pid: Optional[int] = None


class JobSummary(BaseModel):
    """Abbreviated job info for list views."""
    id: str
    type: JobType
    status: JobStatus
    camera: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: JobProgress
    output_file: Optional[str] = None
    error: Optional[str] = None


class FileInfo(BaseModel):
    """Information about an output file."""
    name: str
    path: str
    size: int
    modified: datetime
    is_video: bool = False


class Preset(BaseModel):
    """Saved job configuration preset."""
    id: str
    name: str
    type: JobType
    camera: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class PresetCreate(BaseModel):
    """Request body for creating a preset."""
    name: str
    type: JobType
    camera: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)


class PresetUpdate(BaseModel):
    """Request body for updating a preset."""
    name: Optional[str] = None
    type: Optional[JobType] = None
    camera: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None


class Config(BaseModel):
    """Application configuration."""
    default_camera: Optional[str] = None
    default_base_url: str = "http://127.0.0.1:5000"
    default_recordings_path: str = "/mnt/media/frigate/recordings"
    default_encoder: str = "hevc_nvenc"
    timezone: str = "America/New_York"
    latitude: float = 40.7128
    longitude: float = -74.0060
