import type {
  NormalizedTaskStatus,
  TaskStatus,
} from "../types/taskStatus";

const TASK_STATUSES = new Set<TaskStatus>([
  "pending",
  "planning",
  "running",
  "completed",
  "failed",
  "cancelled",
]);

const TASK_STATUS_LABELS: Record<NormalizedTaskStatus, string> = {
  pending: "等待开始",
  planning: "规划中",
  running: "执行中",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  unknown: "未知状态",
};

const TASK_STATUS_DESCRIPTIONS: Record<NormalizedTaskStatus, string> = {
  pending: "任务已创建，正在等待执行。",
  planning: "任务正在生成执行计划。",
  running: "任务正在执行，请等待处理完成。",
  completed: "任务已经执行完成。",
  failed: "任务执行失败，请查看错误信息。",
  cancelled: "任务已取消，不会继续执行。",
  unknown: "后端返回了当前前端尚未识别的任务状态。",
};

export function normalizeTaskStatus(rawStatus: unknown): NormalizedTaskStatus {
  if (typeof rawStatus !== "string") return "unknown";
  const status = rawStatus.trim().toLowerCase();
  return TASK_STATUSES.has(status as TaskStatus)
    ? (status as TaskStatus)
    : "unknown";
}

export function isTerminalStatus(status: unknown): boolean {
  const normalized = normalizeTaskStatus(status);
  return (
    normalized === "completed" ||
    normalized === "failed" ||
    normalized === "cancelled"
  );
}

export function isRunningStatus(status: unknown): boolean {
  const normalized = normalizeTaskStatus(status);
  return (
    normalized === "pending" ||
    normalized === "planning" ||
    normalized === "running"
  );
}

export function isFailedStatus(status: unknown): boolean {
  return normalizeTaskStatus(status) === "failed";
}

export function isCompletedStatus(status: unknown): boolean {
  return normalizeTaskStatus(status) === "completed";
}

export function getTaskStatusLabel(status: unknown): string {
  return TASK_STATUS_LABELS[normalizeTaskStatus(status)];
}

export function getTaskStatusDescription(status: unknown): string {
  return TASK_STATUS_DESCRIPTIONS[normalizeTaskStatus(status)];
}
