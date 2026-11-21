# GuardStream: Data Flow & Data Model

These diagrams are drawn from the code: the ORM models in [`backend/app/models.py`](../backend/app/models.py), the Redis access in [`backend/app/redis_client.py`](../backend/app/redis_client.py) and the pipeline in [`backend/app/engine/`](../backend/app/engine/). GitHub renders them directly.

**DFD notation:** rectangles are external entities, numbered rounded boxes are processes, cylinders are data stores.

## DFD Level 0: context diagram

```mermaid
flowchart LR
    SRC["Card transaction source<br/>(built-in simulator)"]
    ANALYST["Fraud analyst<br/>(SOC dashboard)"]
    SYS(("0<br/>GuardStream<br/>fraud detection system"))

    SRC -- "card transactions" --> SYS
    SYS -- "live decisions + KPIs" --> ANALYST
    SYS -- "review queue" --> ANALYST
    ANALYST -- "verdict (approve / block) + notes" --> SYS
    ANALYST -- "simulator controls, fraud burst" --> SYS
```

## DFD Level 1

```mermaid
flowchart TB
    SRC["Transaction simulator"]
    ANALYST["Fraud analyst"]

    P1("1.0<br/>Ingest transaction")
    P2("2.0<br/>Build features")
    P3("3.0<br/>Score risk<br/>rules + Isolation Forest")
    P4("4.0<br/>Persist & broadcast")
    P5("5.0<br/>Review alert")

    D1[("D1 Redis Stream<br/>gs:transactions:incoming")]
    D2[("D2 Redis windows<br/>velocity · last location")]
    D3[("D3 Cardholder profiles<br/>(Redis hash)")]
    D4[("D4 transactions<br/>(PostgreSQL)")]
    D5[("D5 alert_audits<br/>(PostgreSQL)")]

    SRC -- "transaction" --> P1
    P1 -- "XADD" --> D1
    D1 -- "XREADGROUP batch<br/>(pending replayed on restart)" --> P2
    D3 -- "spending profile" --> P2
    D2 -- "tx count, last city/country" --> P2
    P2 -- "update windows<br/>(1 pipelined round-trip)" --> D2
    P2 -- "feature vector" --> P3
    P3 -- "risk score 0-100, decision, reasons" --> P4
    P4 -- "upsert evaluated transaction<br/>(idempotent merge)" --> D4
    P4 -- "XACK" --> D1
    P4 -- "WebSocket: decision + KPIs" --> ANALYST
    D4 -- "REVIEW queue" --> P5
    P5 -- "queue with full context" --> ANALYST
    ANALYST -- "verdict + notes" --> P5
    P5 -- "final decision, reviewer" --> D4
    P5 -- "audit record" --> D5
```

## ERD (PostgreSQL)

```mermaid
erDiagram
    TRANSACTIONS ||--o{ ALERT_AUDITS : "reviewed in"

    TRANSACTIONS {
        string id PK "UUID"
        string card_id "indexed"
        string cardholder_name
        string card_tier
        float amount
        string currency
        string merchant
        string merchant_category
        string city
        string country
        float lat
        float lon
        int local_hour
        datetime timestamp "indexed"
        int rule_score
        float ml_score
        int risk_score "indexed"
        string decision "APPROVE / REVIEW / BLOCK"
        jsonb triggered_rules
        jsonb triggered_reasons
        jsonb features
        jsonb user_baseline
        float processing_ms
        string review_status "nullable, indexed"
        string final_decision
        string reviewed_by "nullable"
        datetime reviewed_at "nullable"
        string sim_pattern "ground truth, never read by the engine"
        datetime created_at
    }

    ALERT_AUDITS {
        int id PK
        string transaction_id FK "ON DELETE CASCADE"
        string action
        string previous_decision
        string new_decision
        string analyst
        text notes "nullable"
        datetime created_at
    }
```

`alert_audits` is append-only: every analyst verdict adds a row, so the history of each decision is kept. A composite index on `(review_status, timestamp)` serves the review queue.

### Redis structures (not relational, shown for completeness)

| Key | Type | Holds | Lifetime |
|---|---|---|---|
| `gs:transactions:incoming` | Stream + consumer group | Incoming transactions until acknowledged | Until `XACK` |
| `gs:vel:{card_id}` | Sorted set | Transaction timestamps for velocity rules | Feature window + 60 s |
| `gs:last:{card_id}` | Hash | Last city, country and position | Geo window + 60 s |
| `gs:profiles` | Hash | Each card's spending profile (JSON) | Seeded at start-up |
