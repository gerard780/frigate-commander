#!/usr/bin/env python3
import argparse
import os
import time

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError, ResumableUploadError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Retry settings
MAX_RETRIES = 5
RETRY_BACKOFF = 1.0  # Initial backoff in seconds


def get_service(client_secret: str, token_path: str, no_browser: bool = False):
    creds = None
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            print(f"Warning: Could not load token file: {e}")
            print("Will attempt to re-authorize...")
            creds = None

    if creds and creds.expired and creds.refresh_token:
        print("Refreshing expired token...")
        try:
            creds.refresh(Request())
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            print("Token refreshed and saved.")
        except RefreshError as e:
            print(f"Token refresh failed: {e}")
            print("Token may be revoked. Deleting and re-authorizing...")
            os.remove(token_path)
            creds = None
        except Exception as e:
            print(f"Unexpected error refreshing token: {e}")
            print("Deleting token and re-authorizing...")
            os.remove(token_path)
            creds = None

    if not creds or not creds.valid:
        if not os.path.exists(client_secret):
            raise SystemExit(f"Client secret file not found: {client_secret}")
        flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
        if no_browser:
            # Manual flow for remote terminals
            import urllib.parse
            # Let Google choose the redirect port (matches Desktop app behavior)
            redirect_uri = "http://localhost:8085/"
            flow.redirect_uri = redirect_uri
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print("\n" + "=" * 60)
            print("STEP 1: Visit this URL to authorize:")
            print(auth_url)
            print("=" * 60)
            print("\nSTEP 2: After authorizing, you'll be redirected to a localhost URL")
            print("        (the page will fail to load - that's OK!)")
            print("\nSTEP 3: Copy the FULL URL from your browser's address bar")
            print("        and paste it below.\n")
            redirect_response = input("Paste redirect URL: ").strip()
            # Extract code from URL
            parsed = urllib.parse.urlparse(redirect_response)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" not in params:
                raise SystemExit("No authorization code found in URL. Make sure you copied the full URL.")
            code = params["code"][0]
            # Extract redirect_uri from the pasted URL to ensure it matches
            actual_redirect = f"{parsed.scheme}://{parsed.netloc}/"
            flow.redirect_uri = actual_redirect
            print(f"Exchanging code for token...")
            flow.fetch_token(code=code)
            creds = flow.credentials
            print("Authorization successful!")
        else:
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
    p.add_argument("--no-browser", action="store_true", default=False,
                   help="Don't open browser for auth. Just print URL (for remote terminals).")
    return p.parse_args()


def resumable_upload(request, retries=MAX_RETRIES, backoff=RETRY_BACKOFF):
    """
    Execute a resumable upload with retry logic.

    Handles transient errors with exponential backoff.
    """
    response = None
    retry_count = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Upload: {int(status.progress() * 100)}%")
            retry_count = 0  # Reset on successful chunk
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                # Retryable server errors
                if retry_count >= retries:
                    raise SystemExit(f"Upload failed after {retries} retries: {e}")
                delay = backoff * (2 ** retry_count)
                print(f"Server error ({e.resp.status}), retrying in {delay:.1f}s... (attempt {retry_count + 1}/{retries})")
                time.sleep(delay)
                retry_count += 1
            elif e.resp.status == 429:
                # Rate limited
                if retry_count >= retries:
                    raise SystemExit(f"Upload rate limited after {retries} retries: {e}")
                delay = backoff * (2 ** retry_count) * 2  # Longer delay for rate limit
                print(f"Rate limited (429), retrying in {delay:.1f}s... (attempt {retry_count + 1}/{retries})")
                time.sleep(delay)
                retry_count += 1
            elif e.resp.status == 403:
                # Check for quota exceeded
                error_reason = ""
                if e.content:
                    try:
                        import json
                        err = json.loads(e.content)
                        error_reason = err.get("error", {}).get("errors", [{}])[0].get("reason", "")
                    except Exception:
                        pass
                if error_reason == "quotaExceeded":
                    raise SystemExit("YouTube API quota exceeded. Try again tomorrow.")
                raise SystemExit(f"Upload forbidden (403): {e}")
            elif e.resp.status == 401:
                raise SystemExit("Upload unauthorized (401). Token may be invalid. Delete token and re-auth.")
            else:
                raise SystemExit(f"Upload failed with HTTP {e.resp.status}: {e}")
        except ResumableUploadError as e:
            if retry_count >= retries:
                raise SystemExit(f"Resumable upload error after {retries} retries: {e}")
            delay = backoff * (2 ** retry_count)
            print(f"Upload error, retrying in {delay:.1f}s... (attempt {retry_count + 1}/{retries})")
            time.sleep(delay)
            retry_count += 1
        except Exception as e:
            # Network errors, timeouts, etc.
            if retry_count >= retries:
                raise SystemExit(f"Upload failed after {retries} retries: {e}")
            delay = backoff * (2 ** retry_count)
            print(f"Error ({type(e).__name__}), retrying in {delay:.1f}s... (attempt {retry_count + 1}/{retries})")
            time.sleep(delay)
            retry_count += 1

    return response


def main():
    args = parse_args()

    # Validate file exists
    if not os.path.exists(args.file):
        raise SystemExit(f"Video file not found: {args.file}")

    service = get_service(args.client_secret, args.token, no_browser=args.no_browser)
    if args.dry_run:
        print("Dry run: authorized and ready to upload.")
        return

    body = {
        "snippet": {"title": args.title, "description": args.description, "tags": args.tags},
        "status": {"privacyStatus": args.privacy},
    }
    media = MediaFileUpload(args.file, chunksize=256 * 1024 * 1024, resumable=True)  # 256MB chunks
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"Uploading: {args.file}")
    print(f"Title: {args.title}")

    response = resumable_upload(request)
    print("Upload complete!")
    print("Video ID:", response["id"])
    print(f"URL: https://www.youtube.com/watch?v={response['id']}")


if __name__ == "__main__":
    main()
