export type TaskStatus =
  | "pending"
  | "planning"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type NormalizedTaskStatus = TaskStatus | "unknown";
