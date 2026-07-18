"""Single source of truth for review question types.

Must stay in sync with the `type` CHECK constraint on the `questions` table
(supabase/migrations/0002_tables.sql). Questions are AI-generated per user from the
lesson content (sub-project #4a); this list is the enum the model must choose from
when producing structured output.
"""

QUESTION_TYPES: list[str] = ["recall", "scenario", "compare", "explain"]


def is_question_type(value: str) -> bool:
    """Return True if `value` is one of the whitelisted question types."""
    return value in QUESTION_TYPES
