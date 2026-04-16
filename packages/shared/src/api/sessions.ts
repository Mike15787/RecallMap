import { apiFetch } from "./client";
import type { ISession } from "../types";

export async function createSession(
  subject?: string,
  examDate?: string
): Promise<ISession> {
  return apiFetch<ISession>("/v1/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: subject ?? null, exam_date: examDate ?? null }),
  });
}

export async function getSession(sessionId: string): Promise<ISession> {
  return apiFetch<ISession>(`/v1/sessions/${sessionId}`);
}
