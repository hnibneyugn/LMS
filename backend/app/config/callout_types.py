"""Single source of truth for review question types.

Must stay in sync with the `type` CHECK constraint on the `questions` table
(supabase/migrations/0002_tables.sql). Questions are AI-generated per user from
the lesson content (sub-project #4a); this is the enum the model must choose
from when producing structured output, plus a Vietnamese description of each
type used to steer that choice inside the prompt.
"""

QUESTION_TYPES: list[str] = ["recall", "scenario", "compare", "explain"]

# Shown to the model so it picks a fitting type per question. Keys must match
# QUESTION_TYPES exactly.
QUESTION_TYPE_DESCRIPTIONS: dict[str, str] = {
    "recall": "Nhớ lại một sự kiện, định nghĩa hoặc chi tiết cụ thể trong bài.",
    "scenario": "Áp dụng kiến thức của bài vào một tình huống thực tế mới.",
    "compare": "So sánh hoặc đối chiếu hai khái niệm, cách tiếp cận trong bài.",
    "explain": "Giải thích nguyên nhân, cơ chế hoặc lý do đằng sau một ý trong bài.",
}
