# SEA SENTINEL V2 — Step 1: Threat Assessment Integration

This package extends the repaired dashboard. It does not require a second Streamlit server.

## Install (Windows / VS Code)

1. Back up your current `C:\Users\User\Sea-Sentinel-V2\app.py`.
2. Extract this ZIP and copy `app.py`, `threat_assessment_page.py`, `assessment/`, `sea_sentinel_runtime.py`, `requirements_sea_sentinel.txt`, `tests/` and `data/` into `C:\Users\User\Sea-Sentinel-V2`. Keep your existing `.streamlit/secrets.toml` unchanged.
3. Open PowerShell in the project directory and run:

```powershell
cd C:\Users\User\Sea-Sentinel-V2
& "C:\Users\User\anaconda3\envs\sea-sentinel-v2\python.exe" -m pip install -r requirements_sea_sentinel.txt
& "C:\Users\User\anaconda3\envs\sea-sentinel-v2\python.exe" -m unittest discover -s tests -v
& "C:\Users\User\anaconda3\envs\sea-sentinel-v2\python.exe" -m streamlit run app.py
```

4. Open `http://localhost:8501`, then select **Threat Assessment** in the existing sidebar.
5. Upload `data/sample_ais.csv`, then inspect scores and export CSV/JSON. The sample is synthetic, and its old timestamps will now be flagged as stale.

## Important boundaries

- This is **CSV-driven operational screening**, not live AIS tracking. No AIS API calls are made.
- Zone entry, route deviation, loitering and visual/AIS mismatch must come from verified upstream data; the assessment engine does not calculate these from a single position.
- The scores are illustrative screening weights and must not be interpreted as probabilities of hostile intent.
- A Low result means no configured indicators were triggered by a complete record, not proof of safety.
- The dashboard's existing image, video and webcam processing are not modified by this integration.

## Next step

Connect real AIS records and independently verified geofence/trajectory processing, then feed those records to the same assessment engine.
