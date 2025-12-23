# Frigate Animal Exporter

Minimal scaffolding for a CLI that exports animal clips from a Frigate instance.

## Setup

1. Create a config file at `~/.config/frigate-animal-exporter/config.toml` (or provide `--config`).
2. Set environment variables for overrides if needed.

Example config:

```toml
[frigate]
url = "https://frigate.local"
auth_token = "your-token"

[recordings]
path = "/srv/frigate/recordings"
```

Environment variables:

- `FRIGATE_URL`
- `FRIGATE_AUTH_TOKEN`
- `FRIGATE_RECORDINGS_PATH`

## Usage

Run the CLI directly with Python:

```bash
python src/cli.py \
  --camera backyard \
  --start 2024-01-01T12:00:00 \
  --end 2024-01-01T13:00:00 \
  --padding 2.5 \
  --merge-gap 5 \
  --render-mode annotated \
  --output /tmp/backyard-animals.mp4
```

Override the config path:

```bash
python src/cli.py \
  --config ./config.toml \
  --camera garage \
  --start 2024-02-01T08:00:00 \
  --end 2024-02-01T09:00:00 \
  --output ./garage-animals.mp4
```
