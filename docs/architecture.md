# Macroscope — Architecture Reference

Versioned diagram of the system from the **Macroscope Design Doc v0.1, §3**.
Rendered from Mermaid; authoritative source is the design doc, not this file.

```mermaid
flowchart TB
    subgraph ingest["INGESTION LAYER"]
        direction LR
        s1["news wires"]
        s2["macro releases"]
        s3["official stats"]
        s4["filings"]
        s5["transcripts"]
        s6["flows"]
    end

    subgraph extract["EVENT EXTRACTION & NORMALIZATION"]
        e1["dedupe"]
        e2["entity resolution"]
        e3["LLM structured extraction"]
        e4["credibility scoring"]
        e5["novelty check"]
    end

    subgraph signals["SIGNAL LIBRARY"]
        sig["S01..Snn objects<br/>(rules + params)"]
    end

    subgraph exposure["TICKER EXPOSURE MANIFESTS"]
        exp["drivers, betas,<br/>channel strengths"]
    end

    subgraph regime["REGIME MODEL"]
        reg["risk-on/off,<br/>rate regime,<br/>liquidity"]
    end

    subgraph prob["PROBABILITY ENGINE"]
        p1["Bayesian combiner (L0)"]
        p2["ML corrector + calibration (L1)"]
        p3["historical analogs"]
    end

    subgraph trade["TRADE CONSTRUCTION &<br/>HOLD-PERIOD PROJECTOR"]
        t1["advisory sizing"]
        t2["hold-duration projector"]
    end

    subgraph report["REPORT GENERATOR"]
        r["Markdown / HTML memo"]
    end

    subgraph review["HUMAN REVIEW LOOP"]
        h1["approve / reject / modify"]
        fs["feedback store"]
    end

    s1 & s2 & s3 & s4 & s5 & s6 --> raw["raw items (timestamped, sourced)"]
    raw --> e1 --> e2 --> e3 --> e4 --> e5
    e5 --> ev["Event objects (JSON)"]

    ev --> sig
    ev --> exp
    ev --> reg

    sig -.->|"signal_strength(t)<br/>× channel × dir<br/>× freshness_decay"| comb
    exp -.-> "exposure manifest" | comb
    reg -.-> "regime gate + tilt" | comb

    comb["Σ signal × channel × dir × decay"] --> p1
    p1 --> p2
    p2 --> p3
    p3 --> probOut["scored thesis object<br/>P(+hurdle) @ 21/63/126/252d"]

    probOut --> t1 --> t2
    t2 --> r
    r --> h1
    h1 --> fs
    fs -.-> "approved/rejected theses →<br/>weight updates" | sig
    fs -.-> "sign revalidation" | reg
```

## Legend

| Element | Role |
|---|---|
| Ingestion Layer | news wires, macro releases, official stats, filings, transcripts, flows |
| Event Extraction | dedupe → entity resolution → LLM structured extraction → credibility scoring → novelty check |
| Signal Library | versioned `{id, input_series, channel_map, sign_prior, half_life_days, strength_fn}` objects |
| Ticker Exposure Manifests | per-ticker driver manifest: betas, channel strengths, customers, catalyst calendar |
| Regime Model | daily classifier → P(risk_on/off/inflation_scare/growth_scare) |
| Probability Engine | L0 transparent combiner + L1 learned corrector + isotonic calibration; analogs for magnitude |
| Trade Construction | advisory volatility-targeted sizing + hold-duration projector (decay/event/thesis-bound) |
| Report Generator | fixed 12-section Markdown/HTML memo with mandatory red-team section |
| Human Review Loop | DRAFT→UNDER_REVIEW→APPROVED→MONITORING→CLOSED; feedback feeds weights |

> Advisory-only system: the engine writes reports only. It never places an order. See design doc §9, §10, §12, §13.
