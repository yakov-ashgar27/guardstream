import { BarChart3, TrendingUp } from "lucide-react";
import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { DECISION_STYLE, riskDecision } from "../lib/format";
import type { TrafficPoint } from "../types/transaction";

const tooltipStyle = {
  contentStyle: { background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#a1a1aa" },
};

/** Live traffic volume (stacked by decision) and risk-score distribution. */
export default function RiskCharts({ traffic, riskScores }: { traffic: TrafficPoint[]; riskScores: number[] }) {
  const histogram = useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, i) => ({ range: `${i * 10}`, count: 0, mid: i * 10 }));
    for (const s of riskScores) bins[Math.min(9, Math.floor(s / 10))].count += 1;
    return bins;
  }, [riskScores]);

  return (
    <div className="grid min-h-0 grid-cols-1 gap-4 lg:grid-cols-5">
      <section className="panel p-4 lg:col-span-3">
        <div className="mb-3 flex items-center justify-between">
          <span className="panel-title">
            <TrendingUp size={14} /> Traffic volume · last 60s
          </span>
          <div className="flex gap-3 text-[11px] text-zinc-500">
            {(["APPROVE", "REVIEW", "BLOCK"] as const).map((d) => (
              <span key={d} className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-sm" style={{ background: DECISION_STYLE[d].hex }} />
                {d.toLowerCase()}
              </span>
            ))}
          </div>
        </div>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={traffic} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <defs>
                {(["APPROVE", "REVIEW", "BLOCK"] as const).map((d) => (
                  <linearGradient key={d} id={`g-${d}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={DECISION_STYLE[d].hex} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={DECISION_STYLE[d].hex} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="time" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false} interval={9} />
              <YAxis allowDecimals={false} tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Area type="monotone" dataKey="approve" stackId="1" stroke={DECISION_STYLE.APPROVE.hex} fill="url(#g-APPROVE)" isAnimationActive={false} />
              <Area type="monotone" dataKey="review" stackId="1" stroke={DECISION_STYLE.REVIEW.hex} fill="url(#g-REVIEW)" isAnimationActive={false} />
              <Area type="monotone" dataKey="block" stackId="1" stroke={DECISION_STYLE.BLOCK.hex} fill="url(#g-BLOCK)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel p-4 lg:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <span className="panel-title">
            <BarChart3 size={14} /> Risk score distribution
          </span>
          <span className="num text-[11px] text-zinc-500">n={riskScores.length}</span>
        </div>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={histogram} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="range" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} scale="sqrt" tick={{ fill: "#71717a", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.03)" }} labelFormatter={(l) => `Score ${l}–${Number(l) + 9}`} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {histogram.map((b) => (
                  <Cell key={b.range} fill={DECISION_STYLE[riskDecision(b.mid)].hex} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
