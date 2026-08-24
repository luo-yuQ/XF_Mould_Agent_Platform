import type { TaskStatus } from "./taskStatus";

export type CollaborationStatus = TaskStatus;

export type CollaborationStepStatus =
  | "pending"
  | "running"
  | "failed"
  | "completed"
  | "skipped";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface CollaborationStep {
  step_id: string;
  step_name: string;
  agent: string;
  status: CollaborationStepStatus;
  input_json: JsonValue;
  output_json: JsonValue;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  model_info_json: Record<string, JsonValue> | null;
  metrics_json: Record<string, JsonValue> | null;
}

export interface CollaborationRun {
  run_id: string;
  status: CollaborationStatus;
  title: string;
  summary: string;
  user_request: string;
  customer_context: Record<string, JsonValue>;
  execution_plan: Array<Record<string, JsonValue>>;
  final_report: string;
  review_result: Record<string, JsonValue>;
  citations: Array<Record<string, JsonValue>>;
  manual_check_items?: string[];
  error: string | null;
  metrics: Record<string, JsonValue> | null;
  created_at: string;
  updated_at: string;
  steps?: CollaborationStep[];
}

export interface CreateSalesProposalRequest {
  user_request: string;
  customer_context?: Record<string, JsonValue>;
  session_id?: string | null;
}

export type CreateSalesProposalResponse = Omit<CollaborationRun, "steps">;
