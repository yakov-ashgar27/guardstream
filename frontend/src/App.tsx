import { ShieldHalf, Wifi, WifiOff } from "lucide-react";
import HeaderStats from "./components/HeaderStats";
import LiveFeed from "./components/LiveFeed";
import ReviewQueue from "./components/ReviewQueue";
import RiskCharts from "./components/RiskCharts";
import SimulatorControls from "./components/SimulatorControls";
import { useTransactionStream } from "./hooks/useTransactionStream";

export default function App() {
  const stream = useTransactionStream();

  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 p-4 lg:p-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15 ring-1 ring-emerald-500/30">
            <ShieldHalf size={20} className="text-emerald-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-zinc-50">GuardStream</h1>
            <p className="text-xs text-zinc-500">Real-time fraud &amp; anomaly detection · SOC console</p>
          </div>
        </div>
        <div
          className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs ring-1 ${
            stream.connected ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30" : "bg-rose-500/10 text-rose-300 ring-rose-500/30"
          }`}
        >
          {stream.connected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {stream.connected ? "Live" : "Reconnecting…"}
        </div>
      </header>

      <HeaderStats stats={stream.stats} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[280px_1fr]">
        <SimulatorControls simulator={stream.simulator} onChange={stream.setSimulator} />
        <RiskCharts traffic={stream.traffic} riskScores={stream.riskScores} />
      </div>

      <div className="grid min-h-[520px] flex-1 grid-cols-1 gap-4 xl:h-[560px] xl:grid-cols-[1fr_400px]">
        <LiveFeed transactions={stream.transactions} />
        <ReviewQueue queue={stream.reviewQueue} onResolved={stream.removeFromQueue} />
      </div>

      <footer className="pb-2 text-center text-[11px] text-zinc-600">
        Hybrid engine: deterministic rules (Redis sliding windows) + Isolation Forest · thresholds 40 / 75
      </footer>
    </div>
  );
}
