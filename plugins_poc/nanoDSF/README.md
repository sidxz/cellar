# nanoDSF Explorer (proof of concept)

A local web app for NanoTemper Prometheus nanoDSF exports. You upload the
raw and processed Excel files for a run, label the capillaries (molecule,
concentration, role) and then:

- overlay any number of curves (ratio, 330 nm, 350 nm, scattering; curve or first derivative)
- see Tm values from the instrument software or recalculated by the app, plus ΔTm against the controls from the same run
- search by molecule, concentration or run, and compare runs side by side
- export figures (SVG/PNG) and the Tm table (CSV)

No data is included in this folder. Runs you import are stored locally in
`library/`, which is git-ignored and should never be committed.

## Run it

1. Install [uv](https://docs.astral.sh/uv/) (one-time):
   `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. From this folder:
   `uv run streamlit run app.py`
   (on macOS you can also double-click `Start nanoDSF Explorer.command`)
3. Your browser opens the app. Go to **Add run** to import a run.

## Files

| File | What it does |
| --- | --- |
| `app.py` | Streamlit app: pages, and the bridge between Python and the UI components |
| `nanodsf_core.py` | Parsing the Prometheus exports, the run library, smoothing, derivatives, Tm / ΔTm |
| `components/overlay_app/` | The Overlay page: capillary tray, plot, legend, Tm table, themes |
| `components/pages_app/` | The Results, Add run and Edit runs pages |
| `.streamlit/config.toml` | Streamlit theme settings |

## How Tm is recalculated

Each signal is put on a 0.1 °C grid and smoothed with a Savitzky–Golay filter
(4 °C window). Peaks in the first derivative are found in the dominant direction,
with a 15 % prominence threshold, ignoring 5 °C at each end. Transitions are
clustered across the run's controls and matched to samples within 10 °C, so T1, T2, …
mean the same thing for the software and recalculated values. Scattering gives
Tagg (aggregation onset) against a flat baseline.
