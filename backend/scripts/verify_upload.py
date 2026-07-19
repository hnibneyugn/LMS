"""One-off end-to-end check against the real R2 bucket and Supabase project.

Drives the real presign -> PUT -> object_exists -> process_file path. It does
NOT go through the HTTP layer, so it does not exercise get_current_user; that
part needs a real magic-link JWT and is checked separately.

Usage: python scripts/verify_upload.py <path-to-file> <file_type> <user_id>
"""

import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from app import db  # noqa: E402
from app.ingest import pipeline  # noqa: E402
from app.storage import r2  # noqa: E402


def main(path: str, file_type: str, user_id: str) -> None:
    data = Path(path).read_bytes()
    file_id = str(uuid.uuid4())
    storage_path = f"{user_id}/{file_id}.{file_type}"
    print(f"file      : {Path(path).name} ({len(data):,} bytes)")

    url = r2.presign_put(storage_path, len(data))
    put = httpx.put(
        url,
        content=data,
        headers={"Content-Length": str(len(data))},
        timeout=180,
    )
    print(f"R2 PUT    : {put.status_code}")
    put.raise_for_status()

    print(f"exists    : {r2.object_exists(storage_path)}")

    db.admin().table("user_files").insert(
        {
            "id": file_id,
            "user_id": user_id,
            "file_name": Path(path).name,
            "file_type": file_type,
            "storage_path": storage_path,
            "file_size": len(data),
            "processing_status": "processing",
        }
    ).execute()

    pipeline.process_file(file_id)

    row = (
        db.admin()
        .table("user_files")
        .select("processing_status, error_message, draft_outline")
        .eq("id", file_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data
    )
    print(f"status    : {row['processing_status']}")
    print(f"error     : {row['error_message']}")

    outline = row["draft_outline"] or []
    print(f"chapters  : {len(outline)}")
    for chapter in outline:
        title = chapter["title"].replace("\n", " ")[:70]
        print(f"  [{chapter['order_index']:>3}] {title} ({len(chapter['content_md'])} chars)")

    over = [c for c in outline if len(c["content_md"]) > 8000]
    print(f"over 8000 : {len(over)}")
    print(f"file_id   : {file_id}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
