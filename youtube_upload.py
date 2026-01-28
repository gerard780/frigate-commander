#!/usr/bin/env python3
"""
youtube_upload.py

Upload videos to YouTube using the YouTube Data API v3.

First-time setup:
1. Go to Google Cloud Console: https://console.cloud.google.com/
2. Create a new project or select existing
3. Enable YouTube Data API v3
4. Create OAuth 2.0 credentials (Desktop application)
5. Download client_secrets.json to this directory
6. Run: python3 youtube_upload.py --setup

Usage:
  python3 youtube_upload.py --file video.mp4 --title "My Video" --description "Description"
"""

import argparse
import os
import sys
import json
import http.client
import httplib2
from pathlib import Path
from typing import Optional

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError:
    print("Required packages not installed. Run:")
    print("  pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)


# Configuration
BASE_DIR = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = BASE_DIR / "client_secret.json"  # Your existing OAuth credentials
TOKEN_DIR = BASE_DIR / "tokens"
DEFAULT_TOKEN_FILE = TOKEN_DIR / "joselyn85.json"  # Your existing token

# Privacy settings
PRIVACY_STATUS = {
    "public": "public",
    "unlisted": "unlisted",
    "private": "private",
}

# Video categories (subset - full list at YouTube API docs)
CATEGORIES = {
    "film": "1",
    "autos": "2",
    "music": "10",
    "pets": "15",
    "sports": "17",
    "travel": "19",
    "gaming": "20",
    "people": "22",
    "comedy": "23",
    "entertainment": "24",
    "news": "25",
    "howto": "26",
    "science": "28",
}


def get_authenticated_service(token_file: Optional[Path] = None):
    """Get an authenticated YouTube service object."""
    credentials = None
    token_path = token_file or DEFAULT_TOKEN_FILE

    # Load existing token
    if token_path.exists():
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            print(f"Warning: Could not load token: {e}")

    # Refresh or get new credentials
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                credentials = None

        if not credentials:
            if not CLIENT_SECRETS_FILE.exists():
                print(f"Error: {CLIENT_SECRETS_FILE} not found.")
                print("\nTo set up YouTube uploads:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project and enable YouTube Data API v3")
                print("3. Create OAuth 2.0 credentials (Desktop application)")
                print("4. Download and save as: client_secrets.json")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_FILE), SCOPES
            )
            credentials = flow.run_local_server(port=0)

        # Save credentials
        TOKEN_DIR.mkdir(exist_ok=True)
        with open(token_path, "w") as f:
            f.write(credentials.to_json())
        print(f"Credentials saved to {token_path}")

    return build("youtube", "v3", credentials=credentials)


def upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: Optional[list] = None,
    category: str = "pets",
    privacy: str = "unlisted",
    progress_callback=None,
    token_file: Optional[Path] = None,
) -> Optional[dict]:
    """
    Upload a video to YouTube.

    Args:
        file_path: Path to the video file
        title: Video title
        description: Video description
        tags: List of tags
        category: Category name (e.g., "pets", "travel")
        privacy: "public", "unlisted", or "private"
        progress_callback: Optional callback(percent, status) for progress updates
        token_file: Optional path to token JSON file (for multi-account support)

    Returns:
        Dict with video ID and URL on success, None on failure
    """
    youtube = get_authenticated_service(token_file=token_file)
    if not youtube:
        return None

    # Validate file
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return None

    file_size = os.path.getsize(file_path)
    print(f"Uploading: {file_path} ({file_size / (1024*1024):.1f} MB)")

    # Build request body
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": CATEGORIES.get(category.lower(), "15"),  # Default: pets
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS.get(privacy.lower(), "unlisted"),
            "selfDeclaredMadeForKids": False,
        },
    }

    # Create upload request
    media = MediaFileUpload(
        file_path,
        chunksize=1024 * 1024,  # 1MB chunks
        resumable=True,
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    # Execute with progress tracking
    response = None
    last_percent = 0

    try:
        while response is None:
            status, response = request.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                if percent != last_percent:
                    last_percent = percent
                    print(f"  Upload progress: {percent}%")
                    if progress_callback:
                        progress_callback(percent, "uploading")

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"\nUpload complete!")
        print(f"  Video ID: {video_id}")
        print(f"  URL: {video_url}")

        if progress_callback:
            progress_callback(100, "complete")

        return {
            "id": video_id,
            "url": video_url,
            "title": title,
            "privacy": privacy,
        }

    except HttpError as e:
        print(f"HTTP error {e.resp.status}: {e.content.decode()}")
        if progress_callback:
            progress_callback(0, f"error: {e.resp.status}")
        return None
    except Exception as e:
        print(f"Upload failed: {e}")
        if progress_callback:
            progress_callback(0, f"error: {e}")
        return None


def check_quota():
    """Check YouTube API quota usage (approximate)."""
    youtube = get_authenticated_service()
    if not youtube:
        return

    # List user's channel to verify access
    try:
        response = youtube.channels().list(
            part="snippet,statistics",
            mine=True,
        ).execute()

        if response.get("items"):
            channel = response["items"][0]
            print(f"Authenticated as: {channel['snippet']['title']}")
            print(f"Subscribers: {channel['statistics'].get('subscriberCount', 'hidden')}")
            print(f"Videos: {channel['statistics']['videoCount']}")
        else:
            print("No channel found for this account")
    except HttpError as e:
        print(f"Error checking quota: {e}")


def main():
    parser = argparse.ArgumentParser(description="Upload videos to YouTube")

    parser.add_argument("--setup", action="store_true",
                        help="Set up OAuth credentials (run once)")
    parser.add_argument("--check", action="store_true",
                        help="Check API access and quota")

    parser.add_argument("--file", "-f", help="Video file to upload")
    parser.add_argument("--title", "-t", help="Video title")
    parser.add_argument("--description", "-d", default="",
                        help="Video description")
    parser.add_argument("--tags", default="",
                        help="Comma-separated tags")
    parser.add_argument("--category", default="pets",
                        choices=list(CATEGORIES.keys()),
                        help="Video category")
    parser.add_argument("--privacy", default="unlisted",
                        choices=["public", "unlisted", "private"],
                        help="Privacy status")
    parser.add_argument("--token-file",
                        help="Path to token JSON file (overrides default)")

    args = parser.parse_args()

    if args.setup or args.check:
        print("Checking YouTube API access...")
        check_quota()
        return

    if not args.file or not args.title:
        parser.print_help()
        print("\nError: --file and --title are required for upload")
        sys.exit(1)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    # Resolve token file path if provided
    token_file = Path(args.token_file) if args.token_file else None

    result = upload_video(
        file_path=args.file,
        title=args.title,
        description=args.description,
        tags=tags,
        category=args.category,
        privacy=args.privacy,
        token_file=token_file,
    )

    if result:
        print(f"\nSuccess! Video available at: {result['url']}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
