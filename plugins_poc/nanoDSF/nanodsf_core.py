"""nanoDSF core: read NanoTemper Prometheus exports, store runs, calculate Tm / ΔTm.

Everything the app shows comes from here. The app (app.py) is only the screen.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

LIBRARY = Path(__file__).parent / "library"
SIGNALS = ["Ratio", "330nm", "350nm", "Scattering"]
SIGNAL_LABELS = {
    "Ratio": "Ratio 350/330",
    "330nm": "330 nm",
    "350nm": "350 nm",
    "Scattering": "Scattering",
}
LAYOUT_COLS = ["Capillary", "Molecule ID", "Concentration", "Units", "Role", "Protein", "Notes"]
TEXT_COLS = ["Molecule ID", "Units", "Role", "Protein", "Notes"]
ROLES = ["sample", "control", "blank", "skip"]

# Tm-finding settings
GRID_STEP = 0.1          # °C between interpolated points
SMOOTH_WINDOW = 4.0      # °C width of the smoothing window
EDGE_IGNORE = 5.0        # °C ignored at the start/end of the ramp (start-up artefacts)
MIN_PEAK_FRACTION = 0.15 # a transition must be ≥15% as clear as the clearest one
MAX_TRANSITIONS = 3
CLUSTER_GAP = 5.0        # °C: control transitions closer than this are the same transition
MATCH_TOLERANCE = 10.0   # °C: a sample transition further than this from every control one is "unmatched"


# --------------------------------------------------------------------------- reading files
def _norm_signal(name) -> str | None:
    n = str(name).lower()
    if "deriv" in n:
        return None
    if "ratio" in n:
        return "Ratio"
    if "330" in n:
        return "330nm"
    if "350" in n:
        return "350nm"
    if "scatter" in n:
        return "Scattering"
    return None


def read_workbook(path) -> dict[str, list[tuple]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = {ws.title: list(ws.iter_rows(values_only=True)) for ws in wb.worksheets}
    wb.close()
    return sheets


def file_kind(sheets) -> str:
    """'raw' or 'processed' (NanoTemper export layouts)."""
    for title, rows in sheets.items():
        if _norm_signal(title) and rows:
            r0 = rows[0]
            if isinstance(r0[0], str) and r0[0].strip().lower().startswith("capillary"):
                return "raw"
            if len(r0) > 1 and str(r0[1]).strip().lower() == "capillary":
                return "processed"
    raise ValueError(
        "This doesn't look like a NanoTemper Prometheus export: "
        "no Ratio / 330nm / 350nm / Scattering sheets in the expected layout."
    )


def _parse_raw_sheet(rows, signal) -> pd.DataFrame:
    """Raw export: per capillary three columns (Time, Temperature, value)."""
    hdr = rows[0]
    df = pd.DataFrame(rows[2:])
    frames = []
    for j in range(0, len(hdr) - 2, 3):
        m = re.search(r"(\d+)", str(hdr[j] or ""))
        if not m:
            continue
        sub = df.iloc[:, j:j + 3].apply(pd.to_numeric, errors="coerce").dropna()
        sub.columns = ["time", "temp", "value"]
        sub.insert(0, "capillary", int(m.group(1)))
        sub.insert(0, "signal", signal)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


def _parse_processed_sheet(rows, signal, curve) -> pd.DataFrame:
    """Processed export: Time, Temperature, then one column per capillary."""
    caps = rows[0]
    df = pd.DataFrame(rows[3:]).apply(pd.to_numeric, errors="coerce")
    frames = []
    for j in range(2, len(caps)):
        if caps[j] is None:
            continue
        sub = pd.DataFrame({"time": df[0], "temp": df[1], "value": df[j]}).dropna()
        sub.insert(0, "capillary", int(caps[j]))
        sub.insert(0, "curve", curve)
        sub.insert(0, "signal", signal)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


def _parse_overview(rows):
    hdr = [str(h).strip() if h is not None else "" for h in rows[0]]
    recs, ids, start = [], {}, None
    for r in rows[1:]:
        if not r or r[0] is None:
            continue
        try:
            cap = int(r[0])
        except (TypeError, ValueError):
            continue
        d = dict(zip(hdr, r))
        sid = d.get("Sample ID")
        ids[cap] = "" if sid is None else str(sid).strip()
        if start is None and isinstance(d.get("Start Time"), datetime):
            start = d["Start Time"]
        for h, v in d.items():
            m = re.match(r"(Onset|Inflection Point)\s*#\s*(\d+)\s*for\s*(.+)$", h, re.I)
            if m and isinstance(v, (int, float)) and not isinstance(v, bool):
                sig = _norm_signal(m.group(3))
                if not sig:
                    continue
                is_onset = m.group(1).lower() == "onset"
                kind = ("Tagg" if sig == "Scattering" else "Onset") if is_onset else "Tm"
                recs.append({"capillary": cap, "signal": sig, "kind": kind,
                             "n": int(m.group(2)), "value": float(v)})
    sw = pd.DataFrame(recs, columns=["capillary", "signal", "kind", "n", "value"])
    return sw, ids, start


def parse_export(path) -> dict:
    sheets = read_workbook(path)
    kind = file_kind(sheets)
    out = {"kind": kind, "curves": None, "software": None, "sample_ids": {}, "start": None}
    frames = []
    for title, rows in sheets.items():
        if title.strip().lower() == "overview":
            out["software"], out["sample_ids"], out["start"] = _parse_overview(rows)
            continue
        if kind == "raw":
            sig = _norm_signal(title)
            if sig:
                frames.append(_parse_raw_sheet(rows, sig))
        else:
            is_deriv = "deriv" in title.lower()
            sig = _norm_signal(re.sub(r"\(.*?\)", "", title))
            if sig:
                frames.append(_parse_processed_sheet(rows, sig, "deriv" if is_deriv else "signal"))
    if not frames:
        raise ValueError(f"No curve sheets found in {Path(path).name}")
    out["curves"] = pd.concat(frames, ignore_index=True)
    return out


# --------------------------------------------------------------------------- library (storage)
def safe_run_id(run_id: str) -> str:
    return re.sub(r"[^\w\-. ]", "_", run_id.strip()).strip() or "Run"


def run_dir(run_id: str) -> Path:
    return LIBRARY / safe_run_id(run_id)


def list_runs() -> list[str]:
    if not LIBRARY.exists():
        return []
    runs = []
    for d in LIBRARY.iterdir():
        if (d / "meta.json").exists():
            runs.append(json.loads((d / "meta.json").read_text())["run_id"])
    return sorted(runs)


def default_layout(caps, sample_ids, protein) -> pd.DataFrame:
    rows = []
    for c in sorted(caps):
        sid = (sample_ids or {}).get(c, "")
        rows.append({"Capillary": c, "Molecule ID": sid or f"Sample {c}", "Concentration": np.nan,
                     "Units": "µM", "Role": "sample", "Protein": protein or "", "Notes": ""})
    return pd.DataFrame(rows, columns=LAYOUT_COLS)


def clean_layout(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in LAYOUT_COLS:
        if c not in df.columns:
            df[c] = np.nan if c == "Concentration" else ""
    df = df[LAYOUT_COLS]
    df["Capillary"] = pd.to_numeric(df["Capillary"], errors="coerce")
    df = df.dropna(subset=["Capillary"])
    df["Capillary"] = df["Capillary"].astype(int)
    df["Concentration"] = pd.to_numeric(df["Concentration"], errors="coerce")
    for c in TEXT_COLS:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["Role"] = df["Role"].str.lower().where(df["Role"].str.lower().isin(ROLES), "sample")
    return df.sort_values("Capillary").reset_index(drop=True)


def layout_from_excel(path_or_buffer, base: pd.DataFrame) -> pd.DataFrame:
    """Read a filled-in layout template and merge it onto an existing layout by capillary."""
    up = pd.read_excel(path_or_buffer) if not str(path_or_buffer).endswith(".csv") else pd.read_csv(path_or_buffer)
    rename = {}
    for col in up.columns:
        for want in LAYOUT_COLS:
            if str(col).strip().lower() == want.lower():
                rename[col] = want
    up = up.rename(columns=rename)
    if "Capillary" not in up.columns:
        raise ValueError("The layout file needs a 'Capillary' column.")
    up = up[[c for c in LAYOUT_COLS if c in up.columns]].dropna(subset=["Capillary"])
    up["Capillary"] = pd.to_numeric(up["Capillary"], errors="coerce").astype("Int64")
    merged = base.set_index("Capillary")
    for _, r in up.iterrows():
        cap = int(r["Capillary"])
        if cap not in merged.index:
            continue
        for c in LAYOUT_COLS[1:]:
            if c in up.columns and pd.notna(r[c]) and str(r[c]).strip() != "":
                merged.loc[cap, c] = r[c]
    return clean_layout(merged.reset_index())


def import_run(paths, run_id, protein="", layout=None, overwrite=False) -> str:
    """Parse raw and/or processed exports and save them in the library as one run."""
    parsed = {}
    for p in paths:
        e = parse_export(p)
        if e["kind"] in parsed:
            raise ValueError(f"Two {e['kind']} files were given; one raw and one processed per run, please.")
        parsed[e["kind"]] = (p, e)
    if "raw" not in parsed:
        raise ValueError("The raw export is required (it's the one with Time/Temperature/value for each capillary).")
    run_id = run_id.strip()
    d = run_dir(run_id)
    if d.exists():
        if not overwrite:
            raise FileExistsError(f"A run called '{run_id}' already exists.")
        shutil.rmtree(d)
    (d / "originals").mkdir(parents=True)

    raw = parsed["raw"][1]
    raw["curves"].to_parquet(d / "raw.parquet", index=False)
    if "processed" in parsed:
        parsed["processed"][1]["curves"].to_parquet(d / "processed.parquet", index=False)
    sw, ids, start = raw["software"], raw["sample_ids"], raw["start"]
    if (sw is None or sw.empty) and "processed" in parsed:
        sw, ids, start = (parsed["processed"][1][k] for k in ("software", "sample_ids", "start"))
    (sw if sw is not None else pd.DataFrame(columns=["capillary", "signal", "kind", "n", "value"])) \
        .to_csv(d / "software_tm.csv", index=False)

    caps = sorted(raw["curves"]["capillary"].unique())
    lay = default_layout(caps, ids, protein)
    if layout is not None:
        lay = layout_from_excel(layout, lay)
    clean_layout(lay).to_csv(d / "layout.csv", index=False)

    for kind, (p, _) in parsed.items():
        shutil.copy2(p, d / "originals" / f"{kind}_{Path(p).name}")
    meta = {"run_id": run_id, "protein": protein, "start_time": start.isoformat() if start else None,
            "imported": datetime.now().isoformat(timespec="seconds"),
            "files": {k: Path(p).name for k, (p, _) in parsed.items()},
            "n_capillaries": len(caps)}
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return run_id


def load_run(run_id: str) -> dict:
    d = run_dir(run_id)
    proc = d / "processed.parquet"
    return {
        "run_id": run_id,
        "meta": json.loads((d / "meta.json").read_text()),
        "raw": pd.read_parquet(d / "raw.parquet"),
        "processed": pd.read_parquet(proc) if proc.exists() else None,
        "software": pd.read_csv(d / "software_tm.csv"),
        "layout": load_layout(run_id),
    }


def load_layout(run_id: str) -> pd.DataFrame:
    df = pd.read_csv(run_dir(run_id) / "layout.csv", dtype={c: str for c in TEXT_COLS}, keep_default_na=False,
                     na_values={"Concentration": [""]})
    return clean_layout(df)


def save_layout(run_id: str, df: pd.DataFrame) -> None:
    clean_layout(df).to_csv(run_dir(run_id) / "layout.csv", index=False)


def save_meta(run_id: str, **changes) -> None:
    p = run_dir(run_id) / "meta.json"
    meta = json.loads(p.read_text())
    meta.update(changes)
    p.write_text(json.dumps(meta, indent=2))


def delete_run(run_id: str) -> None:
    shutil.rmtree(run_dir(run_id))


def run_stamp(run_id: str) -> float:
    d = run_dir(run_id)
    return max(f.stat().st_mtime for f in d.iterdir() if f.is_file())


# --------------------------------------------------------------------------- analysis
def smooth_and_derivative(temp, value, step=GRID_STEP, window=SMOOTH_WINDOW):
    t = np.asarray(temp, float)
    v = np.asarray(value, float)
    order = np.argsort(t)
    t, v = t[order], v[order]
    t, idx = np.unique(t, return_index=True)
    v = v[idx]
    grid = np.arange(t[0], t[-1], step)
    vi = np.interp(grid, t, v)
    n = int(round(window / step)) | 1
    n = min(n, len(grid) - 1 if len(grid) % 2 == 0 else len(grid))
    vs = savgol_filter(vi, n, 2)
    d = savgol_filter(vi, n, 2, deriv=1, delta=step)
    return grid, vs, d


def find_transitions(grid, d) -> list[float]:
    """Temperatures of the clearest peaks in the first derivative (= inflection points / Tm).

    Peaks are looked for in both directions; only the direction of the strongest one is kept
    (ratio usually rises on unfolding, single-wavelength fluorescence usually drops).
    """
    inside = (grid > grid[0] + EDGE_IGNORE) & (grid < grid[-1] - EDGE_IGNORE)
    if not inside.any():
        return []
    dist = max(1, int(3.0 / (grid[1] - grid[0])))
    found = []
    for sign in (1, -1):
        peaks, props = find_peaks(sign * d, prominence=0, distance=dist)
        for p, prom in zip(peaks, props["prominences"]):
            if inside[p]:
                found.append((float(prom), sign, p))
    if not found:
        return []
    best_prom, best_sign, _ = max(found)
    if best_prom <= 0:
        return []
    keep = [f for f in found if f[1] == best_sign and f[0] >= MIN_PEAK_FRACTION * best_prom]
    keep = sorted(keep, reverse=True)[:MAX_TRANSITIONS]
    return sorted(round(float(grid[p]), 2) for _, _, p in keep)


def aggregation_onset(grid, vs) -> float | None:
    """Temperature where scattering starts rising above its early baseline (Tagg onset)."""
    base = (grid > grid[0] + 3) & (grid < grid[0] + 20)
    after = grid >= grid[0] + 20
    if base.sum() < 5 or after.sum() < 5:
        return None
    level = float(np.median(vs[base]))
    rise = vs - level
    sd = float(np.std(rise[base]))
    total = float(rise[after].max())
    if total < max(10 * sd, 5.0):   # rise of less than ~5 mAU: no real aggregation
        return None
    thr = max(5 * sd, 3.0, 0.1 * total)
    above = rise > thr
    w = max(1, int(3.0 / (grid[1] - grid[0])))
    for i in np.where(above & after)[0]:
        if above[i:i + w].all():
            return round(float(grid[i]), 2)
    return None


def recalculated_values(run: dict) -> pd.DataFrame:
    recs = []
    for (sig, cap), g in run["raw"].groupby(["signal", "capillary"]):
        if len(g) < 20:
            continue
        grid, vs, d = smooth_and_derivative(g["temp"], g["value"])
        if sig == "Scattering":
            on = aggregation_onset(grid, vs)
            if on is not None:
                recs.append({"capillary": cap, "signal": sig, "kind": "Tagg", "n": 1, "value": on})
        else:
            for i, t in enumerate(find_transitions(grid, d), 1):
                recs.append({"capillary": cap, "signal": sig, "kind": "Tm", "n": i, "value": t})
    return pd.DataFrame(recs, columns=["capillary", "signal", "kind", "n", "value"])


def _reference_temps(per_control: list[list[float]]) -> list[float]:
    """Group the controls' transitions into shared transitions (T1, T2, ...) and average them."""
    vals = sorted((v, k) for k, lst in enumerate(per_control) for v in lst)
    if not vals:
        return []
    clusters = [[vals[0]]]
    for v in vals[1:]:
        if v[0] - clusters[-1][-1][0] > CLUSTER_GAP:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    need = max(1, int(np.ceil(len(per_control) / 2)))
    return [float(np.mean([x[0] for x in c])) for c in clusters if len({x[1] for x in c}) >= need]


def _match(values: list[float], refs: list[float]) -> dict[int, int]:
    pairs = sorted((abs(v - r), i, j) for i, v in enumerate(values) for j, r in enumerate(refs))
    used_i, used_j, out = set(), set(), {}
    for dist, i, j in pairs:
        if dist > MATCH_TOLERANCE or i in used_i or j in used_j:
            continue
        out[i] = j
        used_i.add(i)
        used_j.add(j)
    return out


def compute_results(run: dict) -> pd.DataFrame:
    """One row per (capillary, signal, method, transition) with Tm, control reference and ΔTm."""
    lay = run["layout"]
    controls = lay.loc[lay["Role"] == "control", "Capillary"].tolist()
    sw = run["software"].copy()
    sw["method"] = "software"
    rc = recalculated_values(run)
    rc["method"] = "recalculated"
    allv = pd.concat([sw, rc], ignore_index=True)
    caps = lay.loc[lay["Role"] != "skip", "Capillary"].tolist()

    groups = {}
    for (sig, method, kind), g in allv.groupby(["signal", "method", "kind"]):
        by_cap = {c: sorted(gg["value"].tolist()) for c, gg in g.groupby("capillary")}
        if kind in ("Tagg", "Onset"):
            by_cap = {c: v[:1] for c, v in by_cap.items()}
            ctrl_vals = [by_cap[c][0] for c in controls if by_cap.get(c)]
            refs = [float(np.mean(ctrl_vals))] if ctrl_vals else []
        else:
            refs = _reference_temps([by_cap[c] for c in controls if c in by_cap])
        groups[(sig, method, kind)] = (by_cap, refs)

    # Name transitions (T1, T2, ...) consistently across software and recalculated values,
    # so the same physical transition gets the same name in both columns.
    names = {}
    for sig in allv["signal"].unique():
        pool = [(r, key) for key, (_, refs) in groups.items() if key[0] == sig and key[2] == "Tm"
                for r in refs]
        pool.sort()
        n, last = 0, None
        for r, key in pool:
            if last is None or r - last > CLUSTER_GAP:
                n += 1
            names[(key, r)] = f"T{n}"
            last = r

    rows = []
    for (sig, method, kind), (by_cap, refs) in groups.items():
        for cap in caps:
            vals = by_cap.get(cap, [])
            if kind in ("Tagg", "Onset"):
                for v in vals:
                    ref = refs[0] if refs else np.nan
                    rows.append((cap, sig, method, kind, kind, v, ref))
                continue
            if refs:
                m = _match(vals, refs)
                for i, v in enumerate(vals):
                    if i in m:
                        ref = refs[m[i]]
                        rows.append((cap, sig, method, kind, names[((sig, method, kind), ref)], v, ref))
                    else:
                        rows.append((cap, sig, method, kind, "unmatched", v, np.nan))
            else:
                for i, v in enumerate(vals, 1):
                    rows.append((cap, sig, method, kind, f"#{i}", v, np.nan))
    res = pd.DataFrame(rows, columns=["Capillary", "Signal", "Method", "Kind", "Transition", "Tm", "Control Tm"])
    res["ΔTm"] = res["Tm"] - res["Control Tm"]
    res.insert(0, "Run", run["run_id"])
    res = res.merge(lay, on="Capillary", how="left")
    return res


def curve(run: dict, capillary: int, signal: str, source: str, view: str):
    """(temperature, values) for plotting. source: 'processed'|'raw'; view: 'signal'|'deriv'."""
    if source == "processed" and run["processed"] is not None:
        p = run["processed"]
        g = p[(p["signal"] == signal) & (p["capillary"] == capillary) & (p["curve"] == view)]
        if not g.empty:
            return g["temp"].to_numpy(), g["value"].to_numpy()
    r = run["raw"]
    g = r[(r["signal"] == signal) & (r["capillary"] == capillary)].sort_values("temp")
    if g.empty:
        return np.array([]), np.array([])
    if view == "signal":
        return g["temp"].to_numpy(), g["value"].to_numpy()
    grid, _, d = smooth_and_derivative(g["temp"], g["value"])
    return grid, d
