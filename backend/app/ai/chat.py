"""Socratic tutor chat for one lesson via Gemini streaming (#5).

No RAG: the whole lesson content goes in the system instruction (D13). The
tutor is strictly Socratic -- it never gives the answer directly, only guiding
questions. Any Gemini failure raises ChatError carrying a Vietnamese message;
it never yields junk and never crashes the request.
"""

import logging
from collections.abc import Iterator

from app.ai.client import CHAT_MODEL, get_client

logger = logging.getLogger(__name__)

_FAILURE_MESSAGE = "Không trả lời được lúc này. Vui lòng thử lại."
_EMPTY_MESSAGE = "Tin nhắn không được để trống."


class ChatError(Exception):
    """Chat call or its stream could not yield a usable reply.

    Its message is Vietnamese and safe to surface to the user.
    """


def _build_system_prompt(content_md: str) -> str:
    return (
        "Bạn là gia sư theo phương pháp Socratic cho một bài học. Chỉ dựa trên "
        "nội dung bài học dưới đây, hãy giúp người học tự hiểu bài.\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "- TUYỆT ĐỐI KHÔNG đưa ra đáp án hay lời giải trực tiếp. Thay vào đó, đặt "
        "1–2 câu hỏi gợi mở dẫn dắt người học tự rút ra câu trả lời.\n"
        "- Ghi nhận phần người học nói đúng; với chỗ chưa đúng hoặc còn thiếu, chỉ "
        "ra bằng câu hỏi để họ suy nghĩ thêm, đừng nói thẳng kết quả.\n"
        "- Nếu người học hỏi điều ngoài phạm vi bài, lịch sự kéo họ về nội dung bài.\n"
        "- Trả lời ngắn gọn, thân thiện, bằng tiếng Việt.\n\n"
        "----- NỘI DUNG BÀI HỌC -----\n"
        f"{content_md}"
    )


def _to_contents(history: list[dict], user_message: str) -> list[dict]:
    """Saved history + the new message -> google-genai `contents`.

    Roles map user->user, assistant->model. The new message is the final user
    turn.
    """
    role_map = {"user": "user", "assistant": "model"}
    contents = [
        {"role": role_map.get(m["role"], "user"), "parts": [{"text": m["content"]}]}
        for m in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


def stream_socratic_reply(
    content_md: str, history: list[dict], user_message: str
) -> Iterator[str]:
    if not user_message or not user_message.strip():
        raise ChatError(_EMPTY_MESSAGE)

    try:
        stream = get_client().models.generate_content_stream(
            model=CHAT_MODEL,
            contents=_to_contents(history, user_message),
            config={"system_instruction": _build_system_prompt(content_md)},
        )
        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text
    except ChatError:
        raise
    except Exception as exc:  # network, quota, malformed stream
        logger.exception("Gemini chat streaming failed")
        raise ChatError(_FAILURE_MESSAGE) from exc
