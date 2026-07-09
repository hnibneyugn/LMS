/**
 * Hand-authored types mirroring the Supabase schema (supabase/migrations/*).
 *
 * Once a live Supabase project exists, regenerate this file with:
 *   supabase gen types typescript --project-id <id> > server/types/database.types.ts
 * Until then, keep it in sync with the migration files by hand.
 */
import type { QuestionType } from '@/server/config/callout-types';

export type ProcessingStatus = 'pending' | 'processing' | 'ready' | 'error';
export type ProgressStatus = 'done' | 'not_done';
export type FileType = 'pdf' | 'docx' | 'pptx' | 'image';

export interface AiFeedback {
  missing_points: string[];
  comment: string;
}

/** A single stored chat message (shape of chat_sessions.messages[] entries). */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface Database {
  public: {
    Tables: {
      user_profiles: {
        Row: {
          id: string;
          display_name: string;
          avatar_url: string | null;
          created_at: string;
        };
        Insert: {
          id: string;
          display_name: string;
          avatar_url?: string | null;
          created_at?: string;
        };
        Update: {
          id?: string;
          display_name?: string;
          avatar_url?: string | null;
          created_at?: string;
        };
      };
      lessons: {
        Row: {
          id: string;
          slug: string;
          title: string;
          week: number | null;
          topic: string | null;
          content_md: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          slug: string;
          title: string;
          week?: number | null;
          topic?: string | null;
          content_md: string;
          updated_at?: string;
        };
        Update: Partial<Database['public']['Tables']['lessons']['Insert']>;
      };
      questions: {
        Row: {
          id: string;
          lesson_id: string | null;
          type: QuestionType;
          question_text: string;
          order_index: number;
        };
        Insert: {
          id?: string;
          lesson_id?: string | null;
          type: QuestionType;
          question_text: string;
          order_index?: number;
        };
        Update: Partial<Database['public']['Tables']['questions']['Insert']>;
      };
      quiz_attempts: {
        Row: {
          id: string;
          user_id: string;
          question_id: string;
          user_answer: string;
          ai_score: number | null;
          ai_feedback: AiFeedback | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          question_id: string;
          user_answer: string;
          ai_score?: number | null;
          ai_feedback?: AiFeedback | null;
          created_at?: string;
        };
        Update: Partial<Database['public']['Tables']['quiz_attempts']['Insert']>;
      };
      lesson_progress: {
        Row: {
          user_id: string;
          lesson_id: string;
          status: ProgressStatus;
          completed_at: string | null;
        };
        Insert: {
          user_id: string;
          lesson_id: string;
          status?: ProgressStatus;
          completed_at?: string | null;
        };
        Update: Partial<Database['public']['Tables']['lesson_progress']['Insert']>;
      };
      chat_sessions: {
        Row: {
          id: string;
          user_id: string;
          lesson_id: string;
          messages: ChatMessage[];
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          lesson_id: string;
          messages?: ChatMessage[];
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database['public']['Tables']['chat_sessions']['Insert']>;
      };
      daily_activity: {
        Row: {
          user_id: string;
          activity_date: string;
          questions_done_count: number;
        };
        Insert: {
          user_id: string;
          activity_date: string;
          questions_done_count?: number;
        };
        Update: Partial<Database['public']['Tables']['daily_activity']['Insert']>;
      };
      user_files: {
        Row: {
          id: string;
          user_id: string;
          lesson_id: string | null;
          file_name: string;
          file_type: FileType;
          storage_path: string;
          file_size: number;
          processing_status: ProcessingStatus;
          error_message: string | null;
          uploaded_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          lesson_id?: string | null;
          file_name: string;
          file_type: FileType;
          storage_path: string;
          file_size: number;
          processing_status?: ProcessingStatus;
          error_message?: string | null;
          uploaded_at?: string;
        };
        Update: Partial<Database['public']['Tables']['user_files']['Insert']>;
      };
      document_chunks: {
        Row: {
          id: string;
          user_id: string;
          user_file_id: string;
          chunk_text: string;
          embedding: number[] | null;
          chunk_index: number;
        };
        Insert: {
          id?: string;
          user_id: string;
          user_file_id: string;
          chunk_text: string;
          embedding?: number[] | null;
          chunk_index: number;
        };
        Update: Partial<Database['public']['Tables']['document_chunks']['Insert']>;
      };
    };
    Views: {
      leaderboard_view: {
        Row: {
          user_id: string | null;
          display_name: string | null;
          avatar_url: string | null;
          lessons_completed: number | null;
          total_questions_done: number | null;
        };
      };
    };
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}
