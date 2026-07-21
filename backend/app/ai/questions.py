"""Generate review questions for one lesson via Gemini structured output (#4a).

No RAG: a lesson is small enough to put whole in the prompt (D13). Any failure
(network, quota, malformed output) raises QuestionGenerationError carrying a
Vietnamese message -- it never returns junk and never crashes the request.
"""

import json
import logging

from pydantic import BaseModel

from app.ai.client import CHAT_MODEL, get_client
from app.config.callout_types import QUESTION_TYPE_DESCRIPTIONS, QUESTION_TYPES

logger = logging.getLogger(__name__)

QUESTION_COUNT = 5
_FAILURE_MESSAGE = "Không sinh được câu hỏi lúc này. Vui lòng thử lại."


class GeneratedQuestion(BaseModel):
    type: str
    question_text: str


class QuestionGenerationError(Exception):
    """Model call or its output could not yield usable questions.

    Its message is Vietnamese and safe to surface to the user.
    """


# JSON Schema handed to Gemini so `type` is constrained to the enum and every
# item carries both fields. Kept as a plain dict (not a Pydantic type) so the
# `enum` maps straight onto QUESTION_TYPES, the single source of truth.
_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": QUESTION_TYPES},
            "question_text": {"type": "string"},
        },
        "required": ["type", "question_text"],
    },
}


def _build_prompt(content_md: str) -> str:
    types_block = "\n".join(
        f"- {name}: {desc}" for name, desc in QUESTION_TYPE_DESCRIPTIONS.items()
    )
    return (
        "Bạn là trợ giảng. Chỉ dựa trên nội dung bài học dưới đây, hãy soạn "
        f"{QUESTION_COUNT} câu hỏi ôn tập tự luận (không phải trắc nghiệm) bằng "
        "tiếng Việt để kiểm tra mức độ hiểu bài của người học.\n\n"
        "Mỗi câu hỏi chọn một loại phù hợp trong các loại sau:\n"
        f"{types_block}\n\n"
        "Yêu cầu: phủ ít nhất 3 trong 4 loại trên; câu hỏi bám sát nội dung, "
        "không hỏi những điều bài không đề cập.\n\n"
        "----- NỘI DUNG BÀI HỌC -----\n"
        f"{content_md}"
    )


def _validate(raw: object) -> list[GeneratedQuestion]:
    """Keep only well-formed items: a known type and non-empty text.

    Diversity ("cover >=3 types") is asked of the model in the prompt but NOT
    enforced here -- a soft requirement must not turn a usable set into a hard
    failure. The hard floor is checked by the caller: at least one item survives.
    """
    if not isinstance(raw, list):
        return []
    valid: list[GeneratedQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        qtype = item.get("type")
        text = item.get("question_text")
        if qtype in QUESTION_TYPES and isinstance(text, str) and text.strip():
            valid.append(GeneratedQuestion(type=qtype, question_text=text.strip()))
    return valid


def generate_questions(content_md: str) -> list[GeneratedQuestion]:
    if not content_md or not content_md.strip():
        raise QuestionGenerationError("Bài học không có nội dung để sinh câu hỏi.")

    try:
        response = get_client().models.generate_content(
            model=CHAT_MODEL,
            contents=_build_prompt(content_md),
            config={
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
            },
        )
        raw = json.loads(response.text)
    except Exception as exc:  # network, quota, malformed JSON, missing .text
        logger.exception("Gemini question generation failed")
        raise QuestionGenerationError(_FAILURE_MESSAGE) from exc

    questions = _validate(raw)
    if not questions:
        raise QuestionGenerationError(_FAILURE_MESSAGE)
    return questions
