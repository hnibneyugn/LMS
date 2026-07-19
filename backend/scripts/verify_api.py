"""One-off live end-to-end check of the whole /api/files flow.

Drives the real HTTP endpoints against the real Supabase project and the real
R2 bucket: presign -> PUT to R2 -> process -> poll until terminal -> read the
draft outline back. Unlike verify_upload.py this DOES exercise JWT verification.

The session token is minted in-process through Supabase's admin API
(generate_link -> verify), so no magic-link email or browser step is needed and
the token is never printed.

Usage: python scripts/verify_api.py <path-to-file> <file_type>
Requires the API to be running on http://localhost:8000.
"""

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

API = "http://localhost:8000"


def mint_access_token() -> str:
    """Exchange an admin-generated magic link for a real user session."""
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    email = os.environ["ADMIN_EMAIL"]
    admin_headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    link = httpx.post(
        f"{base}/auth/v1/admin/generate_link",
        headers=admin_headers,
        json={"type": "magiclink", "email": email},
        timeout=30,
    )
    link.raise_for_status()
    # This project's GoTrue returns the link fields at the top level, not
    # nested under "properties" as some versions of the docs show.
    token_hash = link.json()["hashed_token"]

    session = httpx.post(
        f"{base}/auth/v1/verify",
        headers={"apikey": service_key},
        json={"type": "magiclink", "token_hash": token_hash},
        timeout=30,
    )
    session.raise_for_status()
    return session.json()["access_token"]


def main(path: str, file_type: str) -> None:
    data = Path(path).read_bytes()
    headers = {"Authorization": f"Bearer {mint_access_token()}"}
    print(f"file      : {Path(path).name} ({len(data):,} bytes)")

    presign = httpx.post(
        f"{API}/api/files/presign",
        json={
            "file_name": Path(path).name,
            "file_type": file_type,
            "file_size": len(data),
        },
        headers=headers,
        timeout=30,
    )
    print(f"presign   : {presign.status_code}")
    presign.raise_for_status()
    body = presign.json()
    file_id = body["file_id"]
    print(f"key       : {body['storage_path']}")

    put = httpx.put(
        body["upload_url"],
        content=data,
        headers={"Content-Length": str(len(data))},
        timeout=300,
    )
    print(f"R2 PUT    : {put.status_code}")
    put.raise_for_status()

    started = httpx.post(f"{API}/api/files/{file_id}/process", headers=headers, timeout=30)
    print(f"process   : {started.status_code}")
    started.raise_for_status()

    row = {}
    for _ in range(90):
        row = httpx.get(f"{API}/api/files/{file_id}", headers=headers, timeout=30).json()
        if row["processing_status"] in ("ready_for_review", "error"):
            break
        time.sleep(2)

    print(f"status    : {row['processing_status']}")
    print(f"error     : {row['error_message']}")

    outline = row.get("draft_outline") or []
    print(f"chapters  : {len(outline)}")
    for chapter in outline:
        title = chapter["title"].replace("\n", " ")[:66]
        print(f"  [{chapter['order_index']:>3}] {title} ({len(chapter['content_md'])} chars)")
    print(f"over 8000 : {sum(1 for c in outline if len(c['content_md']) > 8000)}")

    listed = httpx.get(f"{API}/api/files", headers=headers, timeout=30).json()
    print(f"list      : {len(listed)} file(s), newest first = {listed[0]['id'] == file_id}")
    print(f"file_id   : {file_id}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
