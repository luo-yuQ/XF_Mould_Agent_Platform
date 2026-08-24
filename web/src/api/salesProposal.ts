import type {
  CollaborationRun,
  CollaborationStep,
  CreateSalesProposalRequest,
  CreateSalesProposalResponse,
} from "../types/salesProposal";

export type CollaborationRunWithSteps = CollaborationRun & {
  steps: CollaborationStep[];
};

export class SalesProposalRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "SalesProposalRequestError";
    this.status = status;
  }
}

export class SalesProposalStepsError extends SalesProposalRequestError {
  run: CollaborationRun;

  constructor(run: CollaborationRun, error: unknown) {
    const message =
      error instanceof Error ? error.message : "售前方案步骤加载失败";
    const status =
      error instanceof SalesProposalRequestError ? error.status : 0;
    super(message, status);
    this.name = "SalesProposalStepsError";
    this.run = run;
  }
}

function errorMessageFromPayload(payload: unknown): string | null {
  if (typeof payload === "string") {
    return payload.trim() || null;
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }

  const errorPayload = payload as Record<string, unknown>;
  for (const key of ["error", "message", "detail"]) {
    const message = errorMessageFromPayload(errorPayload[key]);
    if (message) return message;
  }

  return null;
}

async function responseError(
  response: Response,
): Promise<SalesProposalRequestError> {
  const fallback = response.statusText
    ? `HTTP ${response.status}: ${response.statusText}`
    : `HTTP ${response.status}`;

  try {
    const payload: unknown = await response.json();
    return new SalesProposalRequestError(
      errorMessageFromPayload(payload) || fallback,
      response.status,
    );
  } catch {
    return new SalesProposalRequestError(fallback, response.status);
  }
}

async function requestJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as T;
}

export function createSalesProposal(
  payload: CreateSalesProposalRequest,
): Promise<CreateSalesProposalResponse> {
  return requestJson<CreateSalesProposalResponse>(
    "/sales/proposals/generate",
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function getSalesProposal(runId: string): Promise<CollaborationRun> {
  return requestJson<CollaborationRun>(
    `/sales/proposals/${encodeURIComponent(runId)}`,
    { credentials: "include" },
  );
}

export function getSalesProposalSteps(
  runId: string,
): Promise<CollaborationStep[]> {
  return requestJson<CollaborationStep[]>(
    `/sales/proposals/${encodeURIComponent(runId)}/steps`,
    { credentials: "include" },
  );
}

export async function getSalesProposalWithSteps(
  runId: string,
): Promise<CollaborationRunWithSteps> {
  const run = await getSalesProposal(runId);
  try {
    const steps = await getSalesProposalSteps(runId);
    return { ...run, steps };
  } catch (error: unknown) {
    throw new SalesProposalStepsError(run, error);
  }
}
