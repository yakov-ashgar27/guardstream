import type { Decision } from "../types/transaction";

export const usd = (n: number, digits = 2) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });

export const compactUsd = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(2)}M` : n >= 10_000 ? `$${(n / 1_000).toFixed(1)}K` : usd(n, 0);

export const pct = (n: number | null | undefined, digits = 1) => (n == null ? "—" : `${(n * 100).toFixed(digits)}%`);

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const COUNTRY_FLAG: Record<string, string> = { IL: "🇮🇱", GB: "🇬🇧", US: "🇺🇸", DE: "🇩🇪", FR: "🇫🇷" };

export const DECISION_STYLE: Record<Decision, { text: string; bg: string; ring: string; bar: string; hex: string }> = {
  APPROVE: { text: "text-emerald-300", bg: "bg-emerald-500/10", ring: "ring-emerald-500/30", bar: "bg-emerald-500", hex: "#10b981" },
  REVIEW: { text: "text-amber-300", bg: "bg-amber-500/10", ring: "ring-amber-500/30", bar: "bg-amber-500", hex: "#f59e0b" },
  BLOCK: { text: "text-rose-300", bg: "bg-rose-500/10", ring: "ring-rose-500/30", bar: "bg-rose-500", hex: "#f43f5e" },
};

export const riskDecision = (score: number): Decision => (score >= 75 ? "BLOCK" : score >= 40 ? "REVIEW" : "APPROVE");
