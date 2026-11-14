import { useCallback, useEffect, useRef, useState } from "react";
import type { SimulatorState, Stats, TrafficPoint, Transaction, WSMessage } from "../types/transaction";

const FEED_LIMIT = 150;
const RISK_SAMPLE_LIMIT = 600;
const TRAFFIC_POINTS = 60;
const FLUSH_MS = 250;

export interface TransactionStream {
  connected: boolean;
  transactions: Transaction[];
  reviewQueue: Transaction[];
  stats: Stats | null;
  simulator: SimulatorState | null;
  traffic: TrafficPoint[];
  riskScores: number[];
  removeFromQueue: (id: string) => void;
  setSimulator: (s: SimulatorState) => void;
}

const wsUrl = () => {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/transactions`;
};

const emptyBucket = (): TrafficPoint => ({
  time: new Date().toLocaleTimeString("en-GB", { minute: "2-digit", second: "2-digit" }),
  approve: 0,
  review: 0,
  block: 0,
});

/**
 * Connects to the backend WebSocket, keeps the live feed / review queue / KPI
 * state, buckets traffic per second for charts, and reconnects with backoff.
 * Incoming transactions are buffered and flushed every 250 ms so the UI stays
 * smooth at high TPS.
 */
export function useTransactionStream(): TransactionStream {
  const [connected, setConnected] = useState(false);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [reviewQueue, setReviewQueue] = useState<Transaction[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [simulator, setSimulator] = useState<SimulatorState | null>(null);
  const [traffic, setTraffic] = useState<TrafficPoint[]>([]);
  const [riskScores, setRiskScores] = useState<number[]>([]);

  const buffer = useRef<Transaction[]>([]);
  const bucket = useRef<TrafficPoint>(emptyBucket());

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case "snapshot": {
        const { recent, review_queue, stats: s, simulator: sim } = msg.data;
        setTransactions(recent);
        setReviewQueue(review_queue);
        setStats(s);
        setSimulator(sim);
        setRiskScores(recent.map((t) => t.risk_score));
        break;
      }
      case "transaction": {
        const tx = msg.data;
        buffer.current.push(tx);
        const key = tx.decision.toLowerCase() as "approve" | "review" | "block";
        bucket.current[key] += 1;
        break;
      }
      case "review_update":
        setReviewQueue((q) => q.filter((t) => t.id !== msg.data.id));
        setTransactions((list) => list.map((t) => (t.id === msg.data.id ? msg.data : t)));
        break;
      case "stats":
        setStats(msg.data);
        break;
      case "simulator":
        setSimulator(msg.data);
        break;
    }
  }, []);

  // WebSocket lifecycle with exponential backoff.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        retry = 0;
        setConnected(true);
      };
      ws.onmessage = (ev) => {
        try {
          handleMessage(JSON.parse(ev.data as string) as WSMessage);
        } catch (err) {
          console.error("Bad WS message", err);
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (closed) return;
        const delay = Math.min(10_000, 500 * 2 ** retry++);
        timer = setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    const ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25_000);
    return () => {
      closed = true;
      clearTimeout(timer);
      clearInterval(ping);
      ws?.close();
    };
  }, [handleMessage]);

  // Flush buffered transactions into React state.
  useEffect(() => {
    const id = setInterval(() => {
      if (buffer.current.length === 0) return;
      const batch = buffer.current.reverse();
      buffer.current = [];
      setTransactions((list) => [...batch, ...list].slice(0, FEED_LIMIT));
      setRiskScores((s) => [...batch.map((t) => t.risk_score), ...s].slice(0, RISK_SAMPLE_LIMIT));
      const newReviews = batch.filter((t) => t.review_status === "PENDING");
      if (newReviews.length) {
        setReviewQueue((q) => [...newReviews, ...q].sort((a, b) => b.risk_score - a.risk_score));
      }
    }, FLUSH_MS);
    return () => clearInterval(id);
  }, []);

  // Close a traffic bucket every second.
  useEffect(() => {
    const id = setInterval(() => {
      const done = bucket.current;
      bucket.current = emptyBucket();
      setTraffic((t) => [...t, done].slice(-TRAFFIC_POINTS));
    }, 1_000);
    return () => clearInterval(id);
  }, []);

  const removeFromQueue = useCallback((id: string) => setReviewQueue((q) => q.filter((t) => t.id !== id)), []);

  return { connected, transactions, reviewQueue, stats, simulator, traffic, riskScores, removeFromQueue, setSimulator };
}
