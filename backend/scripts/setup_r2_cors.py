"""Apply the CORS policy the R2 bucket needs for browser-direct uploads.

The browser PUTs each file straight to R2 using a presigned URL (see
frontend/src/lib/files.ts). That is a cross-origin request, so the browser
first sends a CORS preflight (OPTIONS). Without a CORS policy on the bucket R2
answers the preflight with 403 and the browser blocks the upload before the PUT
is ever sent -- the user sees "Mất kết nối khi đang tải file lên." even though
the server side works fine (boto3/httpx ignore CORS, which is browser-only).

Run this once per bucket, and again whenever the set of frontend origins
changes. Idempotent: it overwrites the bucket's CORS config wholesale.

    python scripts/setup_r2_cors.py

Origins come from ALLOWED_ORIGINS (the same var the backend uses for its own
CORS), so dev and production stay in sync from one place. Add the deployed
frontend origin there when the app goes live.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

from app.config import settings  # noqa: E402
from app.storage.r2 import _client  # noqa: E402


def _origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


def main() -> None:
    bucket = settings.r2_bucket()
    origins = _origins()
    rules = [
        {
            "AllowedOrigins": origins,
            # The browser only ever PUTs to R2 (uploads); downloads go through
            # the backend. GET is included so a future direct-download would
            # not need a second policy change.
            "AllowedMethods": ["PUT", "GET"],
            # The preflight for the upload asks for content-type; content-length
            # is signed into the URL and sent by the browser automatically.
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }
    ]

    client = _client()
    client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={"CORSRules": rules},
    )

    applied = client.get_bucket_cors(Bucket=bucket)["CORSRules"]
    print(f"bucket : {bucket}")
    print(f"origins: {origins}")
    print("CORS applied:")
    print(json.dumps(applied, indent=2))


if __name__ == "__main__":
    main()
