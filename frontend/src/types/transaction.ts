export type Decision = "APPROVE" | "REVIEW" | "BLOCK";
export type ReviewStatus = "PENDING" | "CONFIRMED_LEGIT" | "CONFIRMED_FRAUD";

export interface TransactionFeatures {
  amount: number;
  hour_of_day: number;
  distance_from_home_km: number;
  tx_count_last_10m: number;
  amount_ratio_to_user_avg: number;
  ml_raw_score?: number;
}

export interface UserBaseline {
  avg_amount: number;
  home_city: string;
  home_country: string;
  tier: "standard" | "premium";
  typical_categories: string[];
  prior_tx_last_60s: number;
  previous_location: string | null;
}

export interface Transaction {
  id: string;
  card_id: string;
  cardholder_name: string;
  card_tier: string;
  amount: number;
  currency: string;
  merchant: string;
  merchant_category: string;
  city: string;
  country: string;
  lat: number;
  lon: number;
  local_hour: number;
  timestamp: string;
  rule_score: number;
  ml_score: number;
  risk_score: number;
  decision: Decision;
  triggered_rules: string[];
  triggered_reasons: string[];
  features: TransactionFeatures;
  user_baseline: UserBaseline;
  processing_ms: number;
  review_status: ReviewStatus | null;
  final_decision: Decision;
  reviewed_by: string | null;
  reviewed_at: string | null;
  sim_pattern: string | null;
}

export interface Stats {
  tps: number;
  total_processed: number;
  total_blocked: number;
  total_review: number;
  pending_reviews: number;
  blocked_amount: number;
  flagged_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  detection_rate: number | null;
  false_positive_rate: number | null;
}

export interface SimulatorState {
  running: boolean;
  tps: number;
  fraud_rate: number;
  max_tps: number;
  generated: number;
  fraud_injected: number;
}

export interface Snapshot {
  recent: Transaction[];
  review_queue: Transaction[];
  stats: Stats;
  simulator: SimulatorState;
}

export type WSMessage =
  | { type: "snapshot"; data: Snapshot }
  | { type: "transaction"; data: Transaction }
  | { type: "review_update"; data: Transaction }
  | { type: "stats"; data: Stats }
  | { type: "simulator"; data: SimulatorState };

export interface TrafficPoint {
  time: string;
  approve: number;
  review: number;
  block: number;
}
