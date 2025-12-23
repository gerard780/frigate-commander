from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import tomllib

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "frigate-animal-exporter" / "config.toml"


@dataclass(frozen=True)
class AppConfig:
    frigate_url: str
    auth_token: str | None
    recordings_path: Path



def _read_config_file(config_path: Path) -> dict:
    if not config_path.exists():
        return {}

    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)



def load_config(config_path: Path | None = None) -> AppConfig:
    config_path = config_path or DEFAULT_CONFIG_PATH
    config_data = _read_config_file(config_path)

    frigate_url = os.getenv("FRIGATE_URL") or config_data.get("frigate", {}).get("url")
    auth_token = os.getenv("FRIGATE_AUTH_TOKEN") or config_data.get("frigate", {}).get("auth_token")
    recordings_path = os.getenv("FRIGATE_RECORDINGS_PATH") or config_data.get("recordings", {}).get("path")

    if not frigate_url:
        raise ValueError("Frigate URL is required. Set FRIGATE_URL or add frigate.url to config.")

    if not recordings_path:
        raise ValueError(
            "Recordings path is required. Set FRIGATE_RECORDINGS_PATH or add recordings.path to config."
        )

    return AppConfig(
        frigate_url=frigate_url,
        auth_token=auth_token,
        recordings_path=Path(recordings_path).expanduser(),
    )
