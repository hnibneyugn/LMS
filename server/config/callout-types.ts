/**
 * Whitelist of Obsidian callout types that the Markdown parser treats as review questions.
 *
 * This is the SINGLE SOURCE OF TRUTH for question types. It must stay in sync with the
 * `type` CHECK constraint on the `questions` table (supabase/migrations/0002_tables.sql).
 * The parser (added in a later pass) reads `> [!<type>]` callouts and keeps only the ones
 * whose type is in QUESTION_TYPES.
 */
export const QUESTION_TYPES = ['recall', 'scenario', 'compare', 'explain'] as const;

export type QuestionType = (typeof QUESTION_TYPES)[number];

/** Type guard: is `value` one of the whitelisted question types? */
export function isQuestionType(value: string): value is QuestionType {
  return (QUESTION_TYPES as readonly string[]).includes(value);
}
