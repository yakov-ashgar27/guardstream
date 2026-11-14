import { DECISION_STYLE, riskDecision } from "../lib/format";
import type { Decision } from "../types/transaction";

export function DecisionBadge({ decision }: { decision: Decision }) {
  const s = DECISION_STYLE[decision];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-semibold tracking-wider ring-1 ${s.bg} ${s.text} ${s.ring}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.bar}`} />
      {decision}
    </span>
  );
}

export function RiskBar({ score }: { score: number }) {
  const s = DECISION_STYLE[riskDecision(score)];
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-zinc-800">
        <div className={`h-full rounded-full ${s.bar} transition-all`} style={{ width: `${Math.max(score, 2)}%` }} />
      </div>
      <span className={`num w-7 text-right text-xs ${s.text}`}>{score}</span>
    </div>
  );
}
