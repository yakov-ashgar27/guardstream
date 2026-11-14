import { Activity, Gauge, ShieldCheck, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { compactUsd, pct } from "../lib/format";
import type { Stats } from "../types/transaction";

interface KpiProps {
  label: string;
  value: ReactNode;
  sub: ReactNode;
  icon: ReactNode;
  accent: string;
}

function Kpi({ label, value, sub, icon, accent }: KpiProps) {
  return (
    <div className="panel relative overflow-hidden p-4">
      <div className={`absolute inset-x-0 top-0 h-px ${accent}`} />
      <div className="flex items-start justify-between">
        <span className="panel-title">{label}</span>
        <span className="text-zinc-500">{icon}</span>
      </div>
      <div className="num mt-3 text-3xl font-semibold text-zinc-50">{value}</div>
      <div className="mt-1 text-xs text-zinc-500">{sub}</div>
    </div>
  );
}

/** Top KPI bar: throughput, money saved, analyst backlog and engine latency. */
export default function HeaderStats({ stats }: { stats: Stats | null }) {
  const s = stats;
  const latencyColor = !s ? "text-zinc-50" : s.avg_latency_ms < 20 ? "text-emerald-300" : s.avg_latency_ms < 50 ? "text-amber-300" : "text-rose-300";
  return (
    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi
        label="Transactions / sec"
        icon={<Activity size={16} />}
        accent="bg-gradient-to-r from-transparent via-sky-500/60 to-transparent"
        value={s ? s.tps.toFixed(1) : "—"}
        sub={s ? <><span className="num">{s.total_processed.toLocaleString()}</span> processed · flagged {pct(s.flagged_rate)}</> : "waiting for stream…"}
      />
      <Kpi
        label="Fraud prevented"
        icon={<ShieldCheck size={16} />}
        accent="bg-gradient-to-r from-transparent via-emerald-500/60 to-transparent"
        value={<span className="text-emerald-300">{s ? compactUsd(s.blocked_amount) : "—"}</span>}
        sub={s ? <><span className="num">{s.total_blocked.toLocaleString()}</span> blocked · detection {pct(s.detection_rate)}</> : "—"}
      />
      <Kpi
        label="Pending reviews"
        icon={<ShieldAlert size={16} />}
        accent="bg-gradient-to-r from-transparent via-amber-500/60 to-transparent"
        value={<span className={s && s.pending_reviews > 0 ? "text-amber-300" : ""}>{s ? s.pending_reviews : "—"}</span>}
        sub={s ? <>false-positive rate {pct(s.false_positive_rate, 2)}</> : "—"}
      />
      <Kpi
        label="Engine latency"
        icon={<Gauge size={16} />}
        accent="bg-gradient-to-r from-transparent via-violet-500/60 to-transparent"
        value={<span className={latencyColor}>{s ? `${s.avg_latency_ms.toFixed(1)}` : "—"}<span className="ml-1 text-base text-zinc-500">ms</span></span>}
        sub={s ? <>p95 <span className="num">{s.p95_latency_ms.toFixed(1)} ms</span> · SLA &lt; 50 ms</> : "—"}
      />
    </section>
  );
}
