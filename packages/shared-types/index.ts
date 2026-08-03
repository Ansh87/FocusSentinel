// Shared TypeScript types for apps/web-dashboard and apps/browser-extension.
// Mirrors services/api/app/schemas.py; kept as a hand-synced copy (no shared
// build step yet) so either app can import these directly via a relative
// path or a workspace package reference once this repo adopts a monorepo
// build tool (Turborepo/Nx) in a later phase.

export type WarningLevel = "none" | "progress_notice" | "warning_one" | "warning_two" | "restricted";

export interface EvaluationResult {
  identifier: string;
  level: WarningLevel;
  message: string;
  minutes_used: number;
  limit_minutes: number | null;
  minutes_remaining: number | null;
  seconds_until_restriction?: number | null;
}

export interface UsageEventInput {
  identifier: string;
  category_key?: string;
  started_at: string; // ISO 8601
  ended_at: string;
  active_duration_seconds: number;
  classification_source: "catalog" | "manual" | "auto_detected";
  idempotency_key: string;
}

export type ActivityCategoryKey =
  | "games"
  | "short_form_video"
  | "social_media"
  | "entertainment_video"
  | "messaging"
  | "educational"
  | "productivity"
  | "creative_work"
  | "reading_research"
  | "other";

export interface TodayUsage {
  student_id: string;
  date: string;
  total_seconds_by_category: Record<string, number>;
  active_warnings: { rule_id: string; level: number; minutes_used: number }[];
  active_restrictions: { rule_id: string; reason: string; scheduled_reset_at: string }[];
}

export type ExtensionReasonCode = "friends" | "special_event" | "school_related" | "technical_issue" | "other";

export interface ExtensionRequest {
  id: string;
  student_id: string;
  requested_minutes: number | null;
  reason_code: ExtensionReasonCode;
  status: "pending" | "approved" | "denied";
}
