"""Socratic chatbot for one lesson (#5).

One chat_sessions row per (user, lesson): a persistent conversation. db.admin()
bypasses RLS, so every query filters user_id explicitly and another user's
lesson is 404, never 403. The reply streams token-by-token; the user message is
saved BEFORE streaming (so it survives a stream failure) and the assistant
message is appended once the stream finishes.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db
from app.ai.chat import ChatError, stream_socratic_reply
from app.dependencies.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

LESSON_NOT_FOUND = "Không tìm thấy bài học."
EMPTY_MESSAGE = "Tin nhắn không được để trống."


class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)


class MessageOut(BaseModel):
    role: str
    content: str


class HistoryOut(BaseModel):
    messages: list[MessageOut]


class _Repo:
    """Thin data layer on the service-role client. Every query filters user_id."""

    def get_lesson(self, user_id: str, lesson_id: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("id, content_md")
            .eq("id", lesson_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_session(self, user_id: str, lesson_id: str) -> dict | None:
        result = (
            db.admin()
            .table("chat_sessions")
            .select("id, messages")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def create_session(self, user_id: str, lesson_id: str) -> dict:
        result = (
            db.admin()
            .table("chat_sessions")
            .insert({"user_id": user_id, "lesson_id": lesson_id, "messages": []})
            .execute()
        )
        row = result.data[0]
        return {"id": row["id"], "messages": []}

    def update_messages(self, session_id: str, messages: list[dict]) -> None:
        # The table has no on-update trigger, so stamp updated_at here. A Python
        # ISO string is a real timestamptz literal; the string "now()" would be
        # inserted verbatim by PostgREST and rejected.
        db.admin().table("chat_sessions").update(
            {"messages": messages, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", session_id).execute()


repo = _Repo()


def _require_lesson(user_id: str, lesson_id: str) -> dict:
    lesson = repo.get_lesson(user_id, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LESSON_NOT_FOUND)
    return lesson


@router.post("/{lesson_id}")
def chat(
    lesson_id: str,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    message = body.message.strip()
    if not message:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, EMPTY_MESSAGE)

    lesson = _require_lesson(user.user_id, lesson_id)

    session = repo.get_session(user.user_id, lesson_id)
    if session is None:
        try:
            session = repo.create_session(user.user_id, lesson_id)
        except Exception:
            # Lost a race with a concurrent first message (unique index on
            # (user_id, lesson_id)): the other request created the row. Read it
            # back instead of surfacing a raw error.
            session = repo.get_session(user.user_id, lesson_id)
            if session is None:
                raise
    history = session["messages"]
    session_id = session["id"]
    user_msg = {"role": "user", "content": message}

    # Save the user message NOW so a stream failure never loses the question.
    repo.update_messages(session_id, history + [user_msg])

    gen = stream_socratic_reply(lesson["content_md"], history, message)

    # Pull the first chunk eagerly: an up-front failure (quota, network) becomes
    # a clean 502 before the response body starts.
    try:
        first = next(gen)
    except ChatError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    except StopIteration:
        first = ""

    def body_stream():
        parts = [first]
        if first:
            yield first
        try:
            for chunk in gen:
                parts.append(chunk)
                yield chunk
        except ChatError:
            # Mid-stream failure: the body already started, so we cannot change
            # the status. Stop quietly; the partial reply is still saved below.
            # stream_socratic_reply already logged the traceback -- avoid a
            # second one for the same incident.
            logger.warning("Gemini chat stream failed mid-way; saving partial reply")
        text = "".join(parts).strip()
        if text:
            repo.update_messages(
                session_id,
                history + [user_msg, {"role": "assistant", "content": text}],
            )

    return StreamingResponse(body_stream(), media_type="text/plain; charset=utf-8")


@router.get("/{lesson_id}", response_model=HistoryOut)
def history(lesson_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_lesson(user.user_id, lesson_id)
    session = repo.get_session(user.user_id, lesson_id)
    return {"messages": session["messages"] if session else []}


@router.delete("/{lesson_id}", response_model=HistoryOut)
def clear(lesson_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_lesson(user.user_id, lesson_id)
    session = repo.get_session(user.user_id, lesson_id)
    if session is not None:
        repo.update_messages(session["id"], [])
    return {"messages": []}
