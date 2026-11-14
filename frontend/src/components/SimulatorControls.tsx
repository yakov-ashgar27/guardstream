import { Pause, Play, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { SimulatorState } from "../types/transaction";

interface Props {
  simulator: SimulatorState | null;
  onChange: (s: SimulatorState) => void;
}

/** Play/pause, speed and fraud-rate sliders, and the "Trigger Fraud Burst" demo button. */
export default function SimulatorControls({ simulator, onChange }: Props) {
  const [tps, setTps] = useState(4);
  const [fraudRate, setFraudRate] = useState(10);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!simulator) return;
    setTps(simulator.tps);
    setFraudRate(Math.round(simulator.fraud_rate * 100));
  }, [simulator?.tps, simulator?.fraud_rate]); // eslint-disable-line react-hooks/exhaustive-deps

  const push = (body: Parameters<typeof api.updateSimulator>[0]) => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => api.updateSimulator(body).then(onChange).catch(console.error), 200);
  };

  const toggle = async () => {
    if (!simulator) return;
    onChange(await api.updateSimulator({ running: !simulator.running }));
  };

  const burst = async () => {
    setBusy(true);
    try {
      const res = await api.fraudBurst(9);
      setFlash(`${res.injected} attacks injected`);
      setTimeout(() => setFlash(null), 2500);
    } finally {
      setBusy(false);
    }
  };

  const running = simulator?.running ?? false;

  return (
    <section className="panel flex flex-col gap-5 p-4">
      <div className="flex items-center justify-between">
        <span className="panel-title">Traffic simulator</span>
        <span className={`flex items-center gap-1.5 text-[11px] ${running ? "text-emerald-400" : "text-zinc-500"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${running ? "animate-pulse bg-emerald-400" : "bg-zinc-600"}`} />
          {running ? "STREAMING" : "PAUSED"}
        </span>
      </div>

      <button
        onClick={toggle}
        disabled={!simulator}
        className={`flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition ${
          running
            ? "bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
            : "bg-emerald-500/90 text-zinc-950 hover:bg-emerald-400"
        } disabled:opacity-40`}
      >
        {running ? <Pause size={16} /> : <Play size={16} />}
        {running ? "Pause stream" : "Start stream"}
      </button>

      <label className="block">
        <div className="mb-1.5 flex justify-between text-xs text-zinc-400">
          <span>Speed</span>
          <span className="num text-zinc-200">{tps.toFixed(1)} tx/s</span>
        </div>
        <input
          type="range"
          min={0.5}
          max={simulator?.max_tps ?? 15}
          step={0.5}
          value={tps}
          onChange={(e) => {
            const v = Number(e.target.value);
            setTps(v);
            push({ tps: v });
          }}
          className="w-full"
        />
      </label>

      <label className="block">
        <div className="mb-1.5 flex justify-between text-xs text-zinc-400">
          <span>Fraud rate</span>
          <span className="num text-zinc-200">{fraudRate}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={50}
          step={1}
          value={fraudRate}
          onChange={(e) => {
            const v = Number(e.target.value);
            setFraudRate(v);
            push({ fraud_rate: v / 100 });
          }}
          className="w-full"
        />
      </label>

      <button
        onClick={burst}
        disabled={busy || !simulator}
        className="group relative flex items-center justify-center gap-2 overflow-hidden rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2.5 text-sm font-semibold text-rose-200 transition hover:bg-rose-500/20 disabled:opacity-50"
      >
        <Zap size={16} className="transition group-hover:scale-110" />
        Trigger fraud burst
      </button>
      <div className="h-4 text-center text-xs text-rose-300/80">{flash}</div>

      <dl className="grid grid-cols-2 gap-2 border-t border-zinc-800 pt-3 text-xs">
        <dt className="text-zinc-500">Generated</dt>
        <dd className="num text-right text-zinc-300">{simulator?.generated.toLocaleString() ?? "—"}</dd>
        <dt className="text-zinc-500">Attack scenarios</dt>
        <dd className="num text-right text-zinc-300">{simulator?.fraud_injected.toLocaleString() ?? "—"}</dd>
      </dl>
    </section>
  );
}
