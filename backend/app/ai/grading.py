"""Grade one free-text answer to a review question via Gemini structured output (#4).

No RAG: grades using the whole lesson content + question + answer (D8/D13). Any
failure (network, quota, malformed output) raises GradingError with a Vietnamese
message -- it never returns junk and never crashes the request.
"""

import json
import logging

from pydantic import BaseModel

from app.ai.client import CHAT_MODEL, get_client

logger = logging.getLogger(__name__)

_FAILURE_MESSAGE = "Không chấm được bài lúc này. Vui lòng thử lại."


class GradeResult(BaseModel):
    score: float
    missing_points: list[str]
    comment: str


class GradingError(Exception):
    """Grade call or its output could not yield a usable result.

    Its message is Vietnamese and safe to surface to the user.
    """


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "missing_points": {"type": "array", "items": {"type": "string"}},
        "comment": {"type": "string"},
    },
    "required": ["score", "missing_points", "comment"],
}


def _build_prompt(
    content_md: str, question_text: str, question_type: str, user_answer: str
) -> str:
    return (
        "Bạn là giám khảo chấm bài tự luận. Chỉ dựa trên nội dung bài học dưới đây, "
        "hãy chấm câu trả lời của người học theo thang điểm 0–10.\n\n"
        "Trả về:\n"
        "- score: điểm số từ 0 đến 10 (được dùng số thập phân), phản ánh mức độ đúng "
        "và đầy đủ so với nội dung bài.\n"
        "- missing_points: danh sách các ý quan trọng trong bài mà câu trả lời còn "
        "thiếu hoặc sai (để mảng rỗng nếu đã đầy đủ).\n"
        "- comment: một nhận xét ngắn gọn, mang tính xây dựng, bằng tiếng Việt.\n\n"
        "Chấm công bằng, bám sát nội dung bài; không trừ điểm vì những gì bài không đề cập.\n\n"
        f"----- NỘI DUNG BÀI HỌC -----\n{content_md}\n\n"
        f"----- CÂU HỎI (loại: {question_type}) -----\n{question_text}\n\n"
        f"----- CÂU TRẢ LỜI CỦA NGƯỜI HỌC -----\n{user_answer}"
    )


def _validate(raw: object) -> GradeResult:
    """Coerce the model's JSON into a GradeResult or raise GradingError.

    score is clamped into [0, 10] (an out-of-range number is corrected, not
    rejected). missing_points must be a list of strings; blank entries are
    dropped. comment must be a string.
    """
    if not isinstance(raw, dict):
        raise GradingError(_FAILURE_MESSAGE)

    score = raw.get("score")
    missing = raw.get("missing_points")
    comment = raw.get("comment")

    # bool is an int subclass -- exclude it so `True` is not read as score 1.
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise GradingError(_FAILURE_MESSAGE)
    if not isinstance(missing, list) or not all(isinstance(m, str) for m in missing):
        raise GradingError(_FAILURE_MESSAGE)
    if not isinstance(comment, str):
        raise GradingError(_FAILURE_MESSAGE)

    clamped = max(0.0, min(10.0, float(score)))
    return GradeResult(
        score=clamped,
        missing_points=[m.strip() for m in missing if m.strip()],
        comment=comment,
    )


def grade_answer(
    content_md: str, question_text: str, question_type: str, user_answer: str
) -> GradeResult:
    if not user_answer or not user_answer.strip():
        raise GradingError("Câu trả lời không được để trống.")

    try:
        response = get_client().models.generate_content(
            model=CHAT_MODEL,
            contents=_build_prompt(
                content_md, question_text, question_type, user_answer
            ),
            config={
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
            },
        )
        raw = json.loads(response.text)
    except Exception as exc:  # network, quota, malformed JSON, missing .text
        logger.exception("Gemini grading failed")
        raise GradingError(_FAILURE_MESSAGE) from exc

    return _validate(raw)
