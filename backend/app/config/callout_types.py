"""Single source of truth for question types the Markdown parser treats as review questions.

Must stay in sync with the `type` CHECK constraint on the `questions` table
(supabase/migrations/0002_tables.sql). The parser (later sub-project) reads
`> [!<type>]` callouts and keeps only those whose type is in QUESTION_TYPES.
"""

QUESTION_TYPES: list[str] = ["recall", "scenario", "compare", "explain"]


def is_question_type(value: str) -> bool:
    """Return True if `value` is one of the whitelisted question types."""
    return value in QUESTION_TYPES
