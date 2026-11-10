"""SEA SENTINEL V2 integrated, upload-based operational risk screening page.
This is not a live AIS connector. Evidence flags must be independently verified.
"""
import json
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from assessment import AssessmentConfig, assess_many

REQUIRED = ["mmsi", "timestamp", "latitude", "longitude", "sog_knots",
            "restricted_zone_entry", "route_deviation_nm", "loitering_minutes", "visual_ais_mismatch"]


def _bool_or_unknown(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return "INVALID"  # engine flags invalid values; never silently coerce


def parse_assessment_csv(upload):
    frame = pd.read_csv(upload, dtype={"mmsi": "string"}, keep_default_na=True)
    absent = [field for field in REQUIRED if field not in frame.columns]
    if absent:
        raise ValueError("Missing required CSV columns: " + ", ".join(absent))
    for field in ("restricted_zone_entry", "visual_ais_mismatch"):
        frame[field] = frame[field].map(_bool_or_unknown)
    frame = frame.astype(object).where(pd.notna(frame), None)
    return frame.to_dict(orient="records")


def render_threat_assessment():
    st.markdown('<div class="eyebrow">SEA SENTINEL / OPERATIONAL INTELLIGENCE</div>', unsafe_allow_html=True)
    st.title("Threat Assessment")
    st.caption("Explainable AIS-based risk screening • Uploaded records • Human review required")
    st.info("Phase 1: evaluate uploaded AIS-enriched records. Live AIS/GPS is NOT connected. YOLO vessel classes and detection confidence are not treated as threat evidence.")

    with st.expander("Assessment policy and configurable thresholds", expanded=False):
        a, b = st.columns(2)
        with a:
            gap = st.number_input("AIS reporting age limit (minutes)", min_value=1.0, value=15.0, step=1.0, key="threat_ais_age")
            speed = st.number_input("Contextual speed limit (knots)", min_value=1.0, value=25.0, step=1.0, key="threat_speed")
        with b:
            route = st.number_input("Route deviation threshold (NM)", min_value=0.1, value=3.0, step=0.5, key="threat_route")
            loiter = st.number_input("Loitering threshold (minutes)", min_value=1.0, value=45.0, step=5.0, key="threat_loiter")
        st.caption("Scores and thresholds are demonstration policy values, not calibrated probabilities. Zone-entry and visual/AIS mismatch flags must be independently verified.")
    cfg = AssessmentConfig(max_ais_age_minutes=gap, speed_limit_knots=speed,
                           route_deviation_nm=route, loitering_minutes=loiter)
    st.subheader("AIS Evidence Input")
    uploaded = st.file_uploader("Upload AIS-enriched CSV", type=["csv"], key="threat_csv_upload")
    with st.expander("CSV format and evidence requirements"):
        st.code(",".join(REQUIRED), language="text")
        st.write("Use ISO 8601 timestamps with timezone (e.g. 2026-11-02T06:00:00Z). Blank evidence fields mean unknown, not false. The CSV must contain precomputed, verified route/zone/loitering indicators; raw AIS alone does not provide them.")
        st.caption("The included sample CSV is synthetic and historical. It is not evidence of real maritime activity.")
    if uploaded is None:
        st.info("Upload a CSV to run the assessment. Try data/sample_ais.csv to test the interface.")
        return
    try:
        records = parse_assessment_csv(uploaded)
        if not records:
            st.warning("The uploaded CSV contains no records.")
            return
        results = assess_many(records, config=cfg, now=datetime.now(timezone.utc))
    except (ValueError, pd.errors.ParserError, UnicodeError) as exc:
        st.error(f"Unable to assess CSV: {exc}")
        return
    counts = {level: sum(r["risk_level"] == level for r in results)
              for level in ("Low", "Moderate", "High", "Insufficient Data")}
    a, b, c, d = st.columns(4)
    a.metric("Assessed records", len(results))
    b.metric("High priority", counts["High"])
    c.metric("Moderate", counts["Moderate"])
    d.metric("Insufficient data", counts["Insufficient Data"])
    summary = pd.DataFrame([{
        "MMSI": r["mmsi"], "Risk level": r["risk_level"], "Screening score": r["score"],
        "Indicators": ", ".join(i["code"].replace("_", " ") for i in r["indicators"]) or "None",
        "Missing fields": ", ".join(r["missing_fields"]),
        "Data errors": "; ".join(r["data_errors"]),
        "AIS age (min)": r["ais_age_minutes"]
    } for r in results])
    st.subheader("Vessel Assessment Results")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.caption("High means priority for operator review; insufficient data is not a Low-risk finding. Stale AIS may produce an alert indicator without a definitive risk level.")
    left, right = st.columns(2)
    with left:
        st.download_button("Download assessment CSV", summary.to_csv(index=False).encode("utf-8"),
                           "sea_sentinel_threat_assessment.csv", "text/csv", use_container_width=True)
    with right:
        st.download_button("Download evidence JSON", json.dumps(results, indent=2).encode("utf-8"),
                           "sea_sentinel_threat_evidence.json", "application/json", use_container_width=True)
    st.subheader("Evidence Inspector")
    selection = st.selectbox("Select record", range(len(results)),
                             format_func=lambda i: f"{i+1}. MMSI {results[i]['mmsi']} — {results[i]['risk_level']}",
                             key="threat_record_select")
    st.json(results[selection])
    st.caption("All uploaded records and results are processed in the current Streamlit session; no live AIS service or persistent incident database is configured.")
