import { Radio } from "lucide-react";
import { useMemo, useState } from "react";
import { clock, COUNTRY_FLAG, usd } from "../lib/format";
import type { Decision, Transaction } from "../types/transaction";
import { DecisionBadge, RiskBar } from "./ui";

const FILTERS: Array<Decision | "ALL"> = ["ALL", "APPROVE", "REVIEW", "BLOCK"];

/** Real-time scrolling transaction table with colour-coded decisions. */
export default function LiveFeed({ transactions }: { transactions: Transaction[] }) {
  const [filter, setFilter] = useState<Decision | "ALL">("ALL");
  const rows = useMemo(
    () => (filter === "ALL" ? transactions : transactions.filter((t) => t.decision === filter)).slice(0, 80),
    [transactions, filter],
  );

  return (
    <section className="panel flex min-h-0 flex-col">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <span className="panel-title">
          <Radio size={14} className="text-emerald-400" /> Live transaction feed
        </span>
        <div className="flex gap-1 rounded-lg bg-zinc-950/60 p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                filter === f ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {f === "ALL" ? "All" : f.charAt(0) + f.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </header>

      <div className="scroll-thin min-h-0 flex-1 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 bg-zinc-900/95 text-[10px] uppercase tracking-wider text-zinc-500 backdrop-blur">
            <tr>
              <th className="px-4 py-2 font-medium">Time</th>
              <th className="px-2 py-2 font-medium">Card</th>
              <th className="px-2 py-2 font-medium">Merchant</th>
              <th className="px-2 py-2 font-medium">Location</th>
              <th className="px-2 py-2 text-right font-medium">Amount</th>
              <th className="px-2 py-2 font-medium">Risk</th>
              <th className="px-2 py-2 font-medium">Decision</th>
              <th className="px-4 py-2 text-right font-medium">Engine</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {rows.map((t) => (
              <tr
                key={t.id}
                title={t.triggered_reasons.join("\n") || "No risk signals"}
                className={`animate-row-in transition-colors hover:bg-zinc-800/40 ${
                  t.decision === "BLOCK" ? "bg-rose-500/[0.04]" : t.decision === "REVIEW" ? "bg-amber-500/[0.03]" : ""
                }`}
              >
                <td className="num whitespace-nowrap px-4 py-2 text-xs text-zinc-500">{clock(t.timestamp)}</td>
                <td className="num whitespace-nowrap px-2 py-2 text-xs text-zinc-300">{t.card_id}</td>
                <td className="max-w-[180px] truncate px-2 py-2">
                  <div className="truncate text-zinc-200">{t.merchant}</div>
                  <div className="text-[10px] uppercase tracking-wide text-zinc-600">{t.merchant_category.replace("_", " ")}</div>
                </td>
                <td className="whitespace-nowrap px-2 py-2 text-xs text-zinc-400">
                  <span className="mr-1">{COUNTRY_FLAG[t.country] ?? "🌐"}</span>
                  {t.city}
                </td>
                <td className="num whitespace-nowrap px-2 py-2 text-right text-zinc-100">{usd(t.amount)}</td>
                <td className="px-2 py-2">
                  <RiskBar score={t.risk_score} />
                </td>
                <td className="px-2 py-2">
                  <DecisionBadge decision={t.final_decision} />
                </td>
                <td className="num whitespace-nowrap px-4 py-2 text-right text-xs text-zinc-500">{t.processing_ms.toFixed(1)} ms</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-16 text-center text-sm text-zinc-600">
                  Waiting for transactions…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
