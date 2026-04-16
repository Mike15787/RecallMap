// ─── 通用 ────────────────────────────────────────────────────────────────────

export type SourceType = "pdf" | "ppt" | "word" | "image" | "notion" | "chatgpt" | "gemini";

// ─── Session ─────────────────────────────────────────────────────────────────

export interface ISession {
  session_id: string;
  created_at: string;
  subject: string | null;
  exam_date: string | null;
  status: string;
  chunk_count: number;
  blind_spot_count: number;
}

// ─── 學習地圖 ─────────────────────────────────────────────────────────────────

export type ZoneType = "blind" | "fuzzy" | "needs_review" | "known";

export interface IMapNode {
  node_id: string;
  concept: string;
  zone: ZoneType;
  comprehension_score: number;   // 0.0–1.0
  retention_score: number;       // 0.0–1.0
  pending_confirmation: boolean;
  next_review_due: string | null;
  intent: "active" | "snoozed" | "archived";
  snooze_until: string | null;
}

export interface ILearningMap {
  session_id: string;
  summary: { known: number; fuzzy: number; blind: number; needs_review: number };
  nodes: IMapNode[];
}

// ─── 盲點 ────────────────────────────────────────────────────────────────────

export interface IBlindSpot {
  concept: string;
  confidence: number;   // 0.0–1.0
  evidence: string[];
  repeat_count: number;
  blind_spot_id: string;
}

// ─── 雙軸掌握度 ───────────────────────────────────────────────────────────────

export interface IComprehensionEvent {
  timestamp: string;
  question_type: "explain" | "apply" | "analogy" | "debug";
  user_answer: string;
  gemma_verdict: "no_understanding" | "partial" | "solid" | "deep";
  gemma_reasoning: string;
  score_delta: number;
  is_delayed_test: boolean;
}

export interface IRetentionEvent {
  timestamp: string;
  question_type: "cloze" | "multiple_choice" | "true_false";
  response_quality: number;   // SM-2：0–5
  new_interval: number;
  new_easiness: number;
}

export interface IMasteryRecord {
  concept_id: string;
  // 理解軸
  comprehension_score: number;
  comprehension_level: "none" | "surface" | "deep" | "transferable";
  pending_confirmation: boolean;
  // 記憶軸
  retention_score: number;
  sm2_interval: number;
  next_review_due: string | null;
  // 意圖
  intent: "active" | "snoozed" | "archived";
  snooze_until: string | null;
}

// ─── 主題 ────────────────────────────────────────────────────────────────────

export interface ITopic {
  topic_id: string;
  name: string;
  description: string;
  language: string;
  chunk_count: number;
  mastery_summary: {
    blind_count: number;
    fuzzy_count: number;
    review_due_count: number;
    known_count: number;
  };
}

// ─── 自適應測驗 ───────────────────────────────────────────────────────────────

export type QuestionType =
  | "short_answer"
  | "multiple_choice"
  | "true_false"
  | "fill_blank"
  | "match_pairs"
  | "sort_items"
  | "image_label";

export type QuizStrategy = "easy_first" | "hard_first" | "random";

export type QuizDomain =
  | "math_formula"
  | "programming"
  | "language"
  | "memorization"
  | "calculation";

export interface IQuiz {
  quiz_id: string;
  topic_id: string;
  domain: QuizDomain;
  concept: string;
  question: string;
  question_type: QuestionType;
  options?: string[];
  formula_tokens?: string[];
  symbol_palette?: string[];
  code_snippet?: string;
  image_ref?: string;
  sort_items?: string[];
  match_pairs?: [string, string][];
  numeric_tolerance?: number;
  hint?: string;
}

export interface IQuizResult {
  quiz_id: string;
  score: number;               // 0.0–1.0
  feedback: string;
  comprehension_updated: number;
  retention_updated: number;
  pending_confirmation: boolean;
  next_review_due: string | null;
}
