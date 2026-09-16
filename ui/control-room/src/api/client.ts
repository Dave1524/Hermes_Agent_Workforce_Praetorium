import type { z } from "zod";
import { type ControlRequest, type ControlResponse, controlResponseSchema } from "./schemas/control";
import { type ProposalRequest, type ProposalResponse, proposalResponseSchema } from "./schemas/proposals";

// Status 0 means the body was unreadable or failed its schema — the API answered, the client could not use it.
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    message?: string,
  ) {
    super(message ?? `HTTP ${status}`);
    this.name = "ApiError";
  }
}

export interface Posted<T> {
  status: number;
  body: T;
}

const CONTROL_HEADERS = { "Content-Type": "application/json", "X-Control-Room": "1" };

const readJson = async (response: Response): Promise<unknown> => {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(response.status, text, `HTTP ${response.status}: not JSON`);
  }
};

const parseOrThrow = <T extends z.ZodType>(schema: T, body: unknown): z.infer<T> => {
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new ApiError(0, body, `unexpected response shape: ${parsed.error.message}`);
  return parsed.data;
};

export const getJson = async <T extends z.ZodType>(path: string, schema: T): Promise<z.infer<T>> => {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await readJson(response);
  if (!response.ok) throw new ApiError(response.status, body);
  return parseOrThrow(schema, body);
};

export const getText = async (path: string): Promise<string> => {
  const response = await fetch(path);
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return response.text();
};

const post = async <T extends z.ZodType>(path: string, payload: unknown, schema: T): Promise<Posted<z.infer<T>>> => {
  const response = await fetch(path, { method: "POST", headers: CONTROL_HEADERS, body: JSON.stringify(payload) });
  const body = await readJson(response);
  return { status: response.status, body: parseOrThrow(schema, body) };
};

export const postControl = (request: ControlRequest): Promise<Posted<ControlResponse>> =>
  post("/api/v1/control/actions", request, controlResponseSchema);

export const postProposal = (request: ProposalRequest): Promise<Posted<ProposalResponse>> =>
  post("/api/v1/control/proposals", request, proposalResponseSchema);
