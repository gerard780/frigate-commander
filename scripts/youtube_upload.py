#!/usr/bin/env python3
import argparse
import os

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_service(client_secret: str, token_path: str):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        print("Refreshing expired token...")
        creds.refresh(Request())
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print("Token refreshed and saved.")
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def parse_args():
    p = argparse.ArgumentParser(description="Upload a video to YouTube (OAuth).")
    p.add_argument("--client-secret", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--tags", nargs="*", default=[])
    p.add_argument("--privacy", default="unlisted", choices=["private", "unlisted", "public"])
    p.add_argument("--dry-run", action="store_true", default=False,
                   help="Authorize and validate inputs without uploading.")
    return p.parse_args()


def main():
    args = parse_args()

    service = get_service(args.client_secret, args.token)
    if args.dry_run:
        print("Dry run: authorized and ready to upload.")
        return
    body = {
        "snippet": {"title": args.title, "description": args.description, "tags": args.tags},
        "status": {"privacyStatus": args.privacy},
    }
    media = MediaFileUpload(args.file, chunksize=-1, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload: {int(status.progress() * 100)}%")
    print("Video ID:", response["id"])


if __name__ == "__main__":
    main()
