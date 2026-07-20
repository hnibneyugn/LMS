"""One-off live end-to-end check of #1b: upload -> review -> confirm -> lessons.

Extends verify_api.py (#1a, which stopped at ready_for_review) through the
confirm phase, and checks the things only a real run can establish:

  * the presigned PUT works the way the BROWSER issues it -- bare body, no
    explicit Content-Length header, a Content-Type the browser would infer.
    ContentLength is signed into the URL (see app/storage/r2.py), so this is
    the step most likely to fail only in production.
  * the numbered-heading heuristic produces sensible chapters on the real
    Vietnamese .docx that motivated it.
  * confirm writes the right lessons: merged content in index order, the
    dropped chapter absent, order_index contiguous from 0.
  * GET /api/files no longer leaks storage_path / user_id.
  * anon key reads 0 rows from lessons (RLS actually on).

Usage: python scripts/verify_1b.py <path-to-file> <file_type>
Requires the API running on http://localhost:8000.
"""

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

API = "http://localhost:8000"

# What a browser sets for these File objects, so the PUT below is shaped like
# the real one rather than like a tidy server-side upload.
BROWSER_CONTENT_TYPE = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "md": "text/markdown",
}


def mint_access_token() -> str:
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
    token_hash = link.json()["hashed_token"]

    session = httpx.post(
        f"{base}/auth/v1/verify",
        headers={"apikey": service_key},
        json={"type": "magiclink", "token_hash": token_hash},
        timeout=30,
    )
    session.raise_for_status()
    return session.json()["access_token"]


def admin_client():
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )


def anon_client():
    from supabase import create_client

    # The anon key lives in the frontend's env file -- it is the browser's key,
    # the backend never uses it except to prove RLS actually bites.
    anon = os.environ.get("SUPABASE_ANON_KEY")
    if not anon:
        for line in Path("../frontend/.env.local").read_text(encoding="utf-8").splitlines():
            if line.startswith("VITE_SUPABASE_ANON_KEY="):
                anon = line.split("=", 1)[1].strip()
    return create_client(os.environ["SUPABASE_URL"], anon)


def main(path: str, file_type: str) -> None:
    data = Path(path).read_bytes()
    headers = {"Authorization": f"Bearer {mint_access_token()}"}
    print(f"file        : {Path(path).name} ({len(data):,} bytes)")

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
    presign.raise_for_status()
    body = presign.json()
    file_id = body["file_id"]
    print(f"presign     : {presign.status_code}  key={body['storage_path']}")

    # THE BROWSER-SHAPED PUT: no explicit Content-Length, plus the Content-Type
    # a browser infers from the File. httpx sets Content-Length itself, exactly
    # as fetch() does.
    put = httpx.put(
        body["upload_url"],
        content=data,
        headers={"Content-Type": BROWSER_CONTENT_TYPE[file_type]},
        timeout=300,
    )
    print(f"R2 PUT      : {put.status_code} (browser-shaped: no explicit Content-Length)")
    if put.status_code != 200:
        print(f"  BODY: {put.text[:500]}")
    put.raise_for_status()

    started = httpx.post(f"{API}/api/files/{file_id}/process", headers=headers, timeout=30)
    print(f"process     : {started.status_code}")
    started.raise_for_status()

    row = {}
    for _ in range(90):
        row = httpx.get(f"{API}/api/files/{file_id}", headers=headers, timeout=30).json()
        if row["processing_status"] in ("ready_for_review", "error"):
            break
        time.sleep(2)

    print(f"status      : {row['processing_status']}   error={row['error_message']}")
    outline = row.get("draft_outline") or []
    print(f"chapters    : {len(outline)}  (chapter_count field = {row.get('chapter_count')})")
    for chapter in outline:
        title = chapter["title"].replace("\n", " ")[:60]
        print(f"   [{chapter['order_index']:>3}] {title} ({len(chapter['content_md'])} chars)")

    if row["processing_status"] != "ready_for_review" or len(outline) < 3:
        print("\n!! not enough chapters to exercise merge+drop; stopping here")
        return

    # ---- payload whitelist -------------------------------------------------
    listed = httpx.get(f"{API}/api/files", headers=headers, timeout=30).json()
    leaked = {k for k in listed[0] if k in ("storage_path", "user_id")}
    print(f"\nlist leaks  : {leaked or 'none'}  (fields={sorted(listed[0])})")

    # ---- confirm: merge 0+1, drop 2, rename ------------------------------
    flat = [{"title": "Bài gộp 0+1", "source_indexes": [0, 1]}] + [
        {"title": f"Bài {i}", "source_indexes": [i]} for i in range(3, len(outline))
    ]
    print(f"confirm     : sending {len(flat)} chapters, dropping draft index 2")
    confirmed = httpx.post(
        f"{API}/api/files/{file_id}/confirm",
        json={"chapters": flat},
        headers=headers,
        timeout=60,
    )
    print(f"              {confirmed.status_code} {confirmed.text[:200]}")
    confirmed.raise_for_status()

    after = httpx.get(f"{API}/api/files/{file_id}", headers=headers, timeout=30).json()
    print(f"file status : {after['processing_status']}")

    # ---- verify the rows that actually landed -----------------------------
    admin = admin_client()
    rows = (
        admin.table("lessons")
        .select("title,slug,order_index,content_md,source_file_id")
        .eq("source_file_id", file_id)
        .order("order_index")
        .execute()
        .data
    )
    print(f"\nlessons     : {len(rows)} rows (expected {len(flat)})")
    for r in rows:
        print(f"   [{r['order_index']:>3}] {r['title'][:40]:<40} {r['slug'][:36]:<36} {len(r['content_md'])} chars")

    merged_ok = rows[0]["content_md"] == (
        outline[0]["content_md"] + "\n\n" + outline[1]["content_md"]
    )
    dropped_ok = all(outline[2]["content_md"] not in r["content_md"] for r in rows)
    order_ok = [r["order_index"] for r in rows] == list(range(len(rows)))
    print(f"\nmerge join  : {'OK' if merged_ok else 'WRONG'}")
    print(f"drop absent : {'OK' if dropped_ok else 'WRONG'}")
    print(f"order_index : {'OK (contiguous from 0)' if order_ok else 'WRONG'}")

    # ---- re-confirm must be refused ---------------------------------------
    again = httpx.post(
        f"{API}/api/files/{file_id}/confirm",
        json={"chapters": flat},
        headers=headers,
        timeout=30,
    )
    print(f"re-confirm  : {again.status_code} {again.json().get('detail')}")
    reprocess = httpx.post(f"{API}/api/files/{file_id}/process", headers=headers, timeout=30)
    print(f"re-process  : {reprocess.status_code} {reprocess.json().get('detail')}")

    # ---- RLS ---------------------------------------------------------------
    anon_rows = anon_client().table("lessons").select("id").execute().data
    print(f"\nanon lessons: {len(anon_rows)} rows (must be 0)")
    print(f"file_id     : {file_id}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
