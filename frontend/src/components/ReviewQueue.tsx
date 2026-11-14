import { Check, ChevronDown, ChevronRight, Inbox, Loader2, ShieldX, UserSearch } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { clock, COUNTRY_FLAG, usd } from "../lib/format";
import type { Transaction } from "../types/transaction";
import { RiskBar } from "./ui";

interface Props {
  queue: Transaction[];
  onResolved: (id: string) => void;
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex justify-between gap-3 py-0.5">
      <span className="text-zinc-500">{label}</span>
      <span className={`num text-right ${highlight ? "text-amber-300" : "text-zinc-300"}`}>{value}</span>
    </div>
  );
}

function CaseDetail({ tx, onResolved }: { tx: Transaction; onResolved: (id: string) => void }) {
  const [pending, setPending] = useState<"APPROVE" | "BLOCK" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const f = tx.features;
  const b = tx.user_baseline;

  const act = async (action: "APPROVE" | "BLOCK") => {
    setPending(action);
    setError(null);
    try {
      await api.review(tx.id, action);
      onResolved(tx.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setPending(null);
    }
  };

  return (
    <div className="space-y-3 border-t border-zinc-800/80 bg-zinc-950/40 px-4 py-3 text-xs">
      <div>
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Risk signals</div>
        <ul className="space-y-1">
          {tx.triggered_reasons.map((r) => (
            <li key={r} className="flex gap-2 text-zinc-300">
              <span className="mt-1.5 h-1 w-1 flex-none rounded-full bg-amber-400" />
              {r}
            </li>
          ))}
        </ul>
        <div className="num mt-2 flex gap-4 text-[11px] text-zinc-500">
          <span>rules +{tx.rule_score}</span>
          <span>ML {tx.ml_score.toFixed(0)}/100</span>
          <span>final {tx.risk_score}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-5">
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">This transaction</div>
          <Row label="Amount" value={usd(tx.amount)} highlight={f.amount_ratio_to_user_avg >= 4 || f.amount_ratio_to_user_avg <= 0.08} />
          <Row label="Local time" value={`${String(f.hour_of_day).padStart(2, "0")}:00`} highlight={f.hour_of_day <= 5} />
          <Row label="Location" value={`${tx.city}, ${tx.country}`} highlight={f.distance_from_home_km > 500} />
          <Row label="Tx last 10m" value={String(f.tx_count_last_10m)} highlight={f.tx_count_last_10m >= 3} />
        </div>
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Cardholder baseline</div>
          <Row label="Avg spend" value={usd(b.avg_amount)} />
          <Row label="Ratio" value={`${f.amount_ratio_to_user_avg.toFixed(2)}×`} highlight={f.amount_ratio_to_user_avg >= 4} />
          <Row label="Home" value={`${b.home_city}, ${b.home_country}`} />
          <Row label="From home" value={`${f.distance_from_home_km.toLocaleString()} km`} highlight={f.distance_from_home_km > 500} />
        </div>
      </div>
      <div className="text-[11px] text-zinc-500">
        {tx.cardholder_name} · {b.tier} tier · usual: {b.typical_categories.join(", ").replace(/_/g, " ")}
        {b.previous_location && <> · previous tx in {b.previous_location}</>}
      </div>

      {error && <div className="rounded-md bg-rose-500/10 px-2 py-1 text-rose-300">{error}</div>}

      <div className="grid grid-cols-2 gap-2 pt-1">
        <button
          onClick={() => act("APPROVE")}
          disabled={pending !== null}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 font-medium text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
        >
          {pending === "APPROVE" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          Confirm legitimate
        </button>
        <button
          onClick={() => act("BLOCK")}
          disabled={pending !== null}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 font-medium text-rose-200 transition hover:bg-rose-500/20 disabled:opacity-50"
        >
          {pending === "BLOCK" ? <Loader2 size={14} className="animate-spin" /> : <ShieldX size={14} />}
          Confirm fraud
        </button>
      </div>
    </div>
  );
}

/** SOC analyst case queue for REVIEW transactions. */
export default function ReviewQueue({ queue, onResolved }: Props) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section className="panel flex min-h-0 flex-col">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <span className="panel-title">
          <UserSearch size={14} className="text-amber-400" /> Analyst review queue
        </span>
        <span className="num rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-300">{queue.length}</span>
      </header>
      <div className="scroll-thin min-h-0 flex-1 overflow-auto">
        {queue.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 py-16 text-sm text-zinc-600">
            <Inbox size={28} />
            Queue is clear
          </div>
        )}
        <ul className="divide-y divide-zinc-800/60">
          {queue.map((tx) => {
            const expanded = open === tx.id;
            return (
              <li key={tx.id} className="animate-row-in">
                <button
                  onClick={() => setOpen(expanded ? null : tx.id)}
                  className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-zinc-800/40 ${expanded ? "bg-zinc-800/30" : ""}`}
                >
                  {expanded ? <ChevronDown size={14} className="text-zinc-500" /> : <ChevronRight size={14} className="text-zinc-500" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="num truncate text-xs text-zinc-300">{tx.card_id}</span>
                      <span className="num text-sm font-medium text-zinc-100">{usd(tx.amount)}</span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-zinc-500">
                      <span className="truncate">
                        {COUNTRY_FLAG[tx.country] ?? "🌐"} {tx.merchant} · {clock(tx.timestamp)}
                      </span>
                      <RiskBar score={tx.risk_score} />
                    </div>
                  </div>
                </button>
                {expanded && <CaseDetail tx={tx} onResolved={onResolved} />}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
