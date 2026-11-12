"""nanoDSF Explorer — the screen. Start it with the 'Start nanoDSF Explorer.command' file.

Every page is a full-window web component (components/overlay_app and components/pages_app);
this file feeds them data and carries out what they ask for (save a layout, import a run, …).
"""
import base64
import re
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import nanodsf_core as core

st.set_page_config(page_title="nanoDSF Explorer", page_icon="🌡️", layout="wide")

# page chrome around the components (the components tint it to match the chosen theme)
st.markdown("""
<style>
.stApp {background:
   radial-gradient(1200px 600px at 85% -10%, rgba(120,140,220,.10), transparent 60%),
   radial-gradient(900px 500px at -10% 10%, rgba(156,195,230,.06), transparent 60%), #0b1020 !important;}
header[data-testid="stHeader"] {background: rgba(11,16,32,.8) !important; backdrop-filter: blur(14px);
   border-bottom: 1px solid rgba(150,170,220,.12);}
.block-container {padding: 3.3rem .9rem 0 !important; max-width: none !important;}
footer {display: none;}
</style>
""", unsafe_allow_html=True)

COMP = Path(__file__).parent / "components"
_overlay = components.declare_component("overlay_app", path=str(COMP / "overlay_app"))
_pages = components.declare_component("pages_app", path=str(COMP / "pages_app"))


# --------------------------------------------------------------------------- cached loading
@st.cache_data(show_spinner=False)
def _load(run_id, stamp):
    return core.load_run(run_id)


@st.cache_data(show_spinner="Calculating Tm…")
def _results(run_id, stamp):
    return core.compute_results(core.load_run(run_id))


def _stamp(run_id):
    # changes when the run's data or the calculation code changes, so old results are never reused
    return (core.run_stamp(run_id), Path(core.__file__).stat().st_mtime)


def load(run_id):
    return _load(run_id, _stamp(run_id))


def results(run_id):
    return _results(run_id, _stamp(run_id))


def fmt_conc(c, units):
    if pd.isna(c):
        return ""
    return f"{c:g} {units}".strip()


def natural_key(s):
    """So 'Sample 2' sorts before 'Sample 10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def runs_sorted():
    return sorted(core.list_runs(), key=natural_key)


def library_version():
    return "|".join(f"{r}:{_stamp(r)}" for r in runs_sorted())


def _pack(arr):
    return [None if not np.isfinite(v) else float(f"{v:.5g}") for v in np.asarray(arr, float)]


def _nn(v):
    return None if pd.isna(v) else float(v)


# --------------------------------------------------------------------------- Overlay data
@st.cache_data(show_spinner="Preparing curves…")
def _overlay_run(run_id, stamp):
    """Everything the Overlay page needs for one run: curves on a shared 0.2 °C grid + Tm results."""
    run = core.load_run(run_id)
    res = core.compute_results(run)
    raw, proc, lay = run["raw"], run["processed"], run["layout"]
    grid = np.round(np.arange(np.ceil(raw["temp"].min() * 5) / 5, raw["temp"].max(), 0.2), 2)
    caps, curves, results_ = [], {}, {}
    for _, r in lay[lay["Role"] != "skip"].iterrows():
        cap = int(r["Capillary"])
        key = f"{run_id}|{cap}"
        caps.append({"key": key, "cap": cap, "mol": r["Molecule ID"], "role": r["Role"], "notes": r["Notes"],
                     "conc": fmt_conc(r["Concentration"], r["Units"]), "concv": _nn(r["Concentration"])})
        cv = {}
        for sig in core.SIGNALS:
            g = raw[(raw["signal"] == sig) & (raw["capillary"] == cap)].sort_values("temp")
            if len(g) < 20:
                continue
            tg, vs, dv = core.smooth_and_derivative(g["temp"], g["value"])
            lo, hi = g["temp"].min(), g["temp"].max()
            out = {"r": np.interp(grid, g["temp"], g["value"], left=np.nan, right=np.nan),
                   "rd": np.interp(grid, tg, dv, left=np.nan, right=np.nan)}
            ps = proc[(proc["signal"] == sig) & (proc["capillary"] == cap)] if proc is not None else pd.DataFrame()
            if not ps.empty:
                for curve, name in (("signal", "s"), ("deriv", "sd")):
                    q = ps[ps["curve"] == curve].sort_values("temp")
                    out[name] = np.interp(grid, q["temp"], q["value"], left=np.nan, right=np.nan)
            else:
                out["s"] = np.interp(grid, tg, vs, left=np.nan, right=np.nan)
                out["sd"] = np.interp(grid, tg, dv, left=np.nan, right=np.nan)
            for k in out:
                out[k][(grid < lo) | (grid > hi)] = np.nan
            cv[sig] = {k: _pack(v) for k, v in out.items()}
        curves[key] = cv
        rr = res[res["Capillary"] == cap]
        results_[key] = [[sg, me, kd, tr, float(tm), _nn(d)] for sg, me, kd, tr, tm, d in
                         zip(rr["Signal"], rr["Method"], rr["Kind"], rr["Transition"], rr["Tm"], rr["ΔTm"])]
    refs = {}
    ref = res[res["Control Tm"].notna()]
    for (sig, meth), g in ref.groupby(["Signal", "Method"]):
        refs.setdefault(sig, {})[meth] = {t: float(v) for t, v in g.groupby("Transition")["Control Tm"].first().items()}
    return {"run": run_id, "protein": run["meta"].get("protein", ""), "caps": caps,
            "grid": _pack(grid), "curves": curves, "results": results_, "refs": refs,
            "n_ctrl": int((lay["Role"] == "control").sum())}


def overlay_payload():
    runs = runs_sorted()
    stamps = [str(_stamp(r)) for r in runs]
    parts = [_overlay_run(r, s) for r, s in zip(runs, stamps)]
    payload = {"runs": [{"run": p["run"], "protein": p["protein"], "caps": p["caps"]} for p in parts],
               "grid": {p["run"]: p["grid"] for p in parts},
               "curves": {k: v for p in parts for k, v in p["curves"].items()},
               "results": {k: v for p in parts for k, v in p["results"].items()},
               "refs": {p["run"]: p["refs"] for p in parts},
               "ctrlCount": {p["run"]: p["n_ctrl"] for p in parts}}
    return payload, "|".join(runs) + "|" + "|".join(stamps)


# --------------------------------------------------------------------------- other pages: data
RESULT_COLS = ["Run", "Capillary", "Molecule ID", "Concentration", "Units", "Role", "Signal", "Method",
               "Kind", "Transition", "Tm", "Control Tm", "ΔTm", "Protein", "Notes"]


def results_payload():
    frames = [results(r) for r in runs_sorted()]
    if not frames:
        return {"cols": RESULT_COLS, "rows": [], "runs": []}
    df = pd.concat(frames, ignore_index=True)[RESULT_COLS]
    rows = []
    for rec in df.itertuples(index=False):
        rows.append([None if (isinstance(v, float) and np.isnan(v)) else (round(v, 3) if isinstance(v, float) else v)
                     for v in rec])
    return {"cols": RESULT_COLS, "rows": rows, "runs": runs_sorted()}


def edit_payload():
    runs = []
    for r in runs_sorted():
        run = load(r)
        lay = run["layout"]
        runs.append({"run": r, "meta": run["meta"], "protein": run["meta"].get("protein", ""),
                     "rows": [{"cap": int(x["Capillary"]), "mol": x["Molecule ID"], "conc": _nn(x["Concentration"]),
                               "units": x["Units"], "role": x["Role"], "protein": x["Protein"], "notes": x["Notes"]}
                              for _, x in lay.iterrows()]})
    return {"runs": runs, "roles": core.ROLES, "units": ["µM", "nM", "mM", "M", "%", "mg/mL", "x"]}


def add_payload():
    pend = st.session_state.get("_pending") or {"files": []}
    start = next((f["start"] for f in pend["files"] if f.get("start")), None)
    suggested = f"Run_{start[:10]}_{start[11:13]}{start[14:16]}" if start else ""
    return {"pending": [{k: f[k] for k in ("name", "kind", "caps", "start")} for f in pend["files"]],
            "suggested": suggested, "runs": runs_sorted(), "saved": st.session_state.get("_saved")}


# --------------------------------------------------------------------------- other pages: actions
def _b64_to_file(folder: Path, name: str, b64: str) -> Path:
    p = folder / Path(name).name
    p.write_bytes(base64.b64decode(b64))
    return p


def handle(page, v):
    """Carry out what a page asked for. Returns the message shown to the user."""
    act = v.get("action")
    if act == "save_layout":
        rows = v["rows"]
        df = pd.DataFrame([{"Capillary": r["cap"], "Molecule ID": r.get("mol") or f"Sample {r['cap']}",
                            "Concentration": r.get("conc"), "Units": r.get("units") or "µM",
                            "Role": r.get("role") or "sample", "Protein": r.get("protein") or "",
                            "Notes": r.get("notes") or ""} for r in rows])
        if v.get("protein") is not None:
            core.save_meta(v["run"], protein=v["protein"])
            df["Protein"] = v["protein"]
        core.save_layout(v["run"], df)
        st.cache_data.clear()
        return f"Saved {v['run']} — Tm and ΔTm recalculated."
    if act == "set_protein":
        run = load(v["run"])
        core.save_meta(v["run"], protein=v["protein"])
        lay = run["layout"].copy()
        lay["Protein"] = v["protein"]
        core.save_layout(v["run"], lay)
        st.cache_data.clear()
        return f"Protein set to “{v['protein']}”."
    if act == "delete_run":
        core.delete_run(v["run"])
        st.cache_data.clear()
        return f"Deleted {v['run']}."
    if act == "import_layout":
        tmp = Path(tempfile.mkdtemp())
        f = _b64_to_file(tmp, v["name"], v["b64"])
        core.save_layout(v["run"], core.layout_from_excel(f, load(v["run"])["layout"]))
        st.cache_data.clear()
        return f"Layout imported from {v['name']}."
    if act == "inspect":
        tmp = Path(tempfile.mkdtemp(prefix="nanodsf_upload_"))
        files = []
        for f in v["files"]:
            p = _b64_to_file(tmp, f["name"], f["b64"])
            e = core.parse_export(p)
            files.append({"path": str(p), "name": f["name"], "kind": e["kind"],
                          "caps": int(e["curves"]["capillary"].nunique()),
                          "start": e["start"].isoformat() if e["start"] else None})
        kinds = [f["kind"] for f in files]
        if len(kinds) != len(set(kinds)):
            raise ValueError("Two files of the same kind — please give one raw and one processed export.")
        st.session_state["_pending"] = {"dir": str(tmp), "files": files}
        st.session_state["_saved"] = None
        return "Files recognised: " + ", ".join(f"{f['name']} → {f['kind']}" for f in files)
    if act == "clear_pending":
        st.session_state["_pending"] = None
        st.session_state["_saved"] = None
        return "Cleared."
    if act == "save_run":
        pend = st.session_state.get("_pending")
        if not pend or not pend["files"]:
            raise ValueError("Add the exported files first.")
        lay = None
        if v.get("layout"):
            lay = _b64_to_file(Path(pend["dir"]), v["layout"]["name"], v["layout"]["b64"])
        rid = core.import_run([f["path"] for f in pend["files"]], v["run_id"], v.get("protein", ""),
                              layout=lay, overwrite=bool(v.get("overwrite")))
        st.cache_data.clear()
        st.session_state["_pending"] = None
        st.session_state["_saved"] = rid
        return f"Saved {rid}."
    raise ValueError(f"Unknown action {act!r}")


def show_page(page, payload, version):
    msg = st.session_state.get("_msg")
    val = _pages(page=page, payload=payload, version=version, msg=msg, key=f"pg_{page}", default=None)
    if val and val.get("nonce") != st.session_state.get(f"_nonce_{page}"):
        st.session_state[f"_nonce_{page}"] = val["nonce"]
        try:
            text, ok = handle(page, val), True
        except Exception as ex:  # noqa: BLE001 — shown to the user
            text, ok = str(ex), False
        st.session_state["_msg"] = {"nonce": f"{time.time()}", "ok": ok, "text": text, "action": val.get("action")}
        st.rerun()


# --------------------------------------------------------------------------- pages
def page_explore():
    if not core.list_runs():
        show_page("empty", {}, "empty")
        return
    payload, version = overlay_payload()
    _overlay(payload=payload, version=version, key="overlay", default=None)


def page_results():
    show_page("results", results_payload(), "results|" + library_version())


def page_add():
    p = add_payload()
    show_page("add", p, "add|" + library_version() + "|" + str(p["pending"]) + str(p["saved"]))


def page_edit():
    show_page("edit", edit_payload(), "edit|" + library_version())


pg = st.navigation([
    st.Page(page_explore, title="Overlay", icon=":material/stacked_line_chart:", default=True),
    st.Page(page_results, title="Results", icon=":material/table_chart:"),
    st.Page(page_add, title="Add run", icon=":material/upload_file:"),
    st.Page(page_edit, title="Edit runs", icon=":material/edit_note:"),
], position="top")
pg.run()
