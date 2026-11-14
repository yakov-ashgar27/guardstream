import type { Decision, SimulatorState, Transaction } from "../types/transaction";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail ?? `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const api = {
  updateSimulator: (body: Partial<Pick<SimulatorState, "running" | "tps" | "fraud_rate">>) =>
    request<SimulatorState>("/api/simulator", { method: "PATCH", body: JSON.stringify(body) }),

  fraudBurst: (size = 8) =>
    request<{ injected: number; patterns: string[] }>("/api/simulator/burst", {
      method: "POST",
      body: JSON.stringify({ size }),
    }),

  review: (id: string, action: Exclude<Decision, "REVIEW">, notes?: string) =>
    request<Transaction>(`/api/transactions/${id}/review`, {
      method: "PATCH",
      body: JSON.stringify({ action, analyst: "soc-analyst", notes }),
    }),
};
