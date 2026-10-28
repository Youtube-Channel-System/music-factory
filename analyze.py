"""Objective quality report for a track: numbers a producer would check before releasing.

    python analyze.py track.mp3 [more.mp3 ...]      # prints a scorecard per file
    python analyze.py --csv report.csv folder/*.mp3

Measures (all with numpy + ffmpeg, no extra libraries):
  loudness      integrated LUFS, loudness range, true peak, sample peak
  tonal balance share of energy in sub / bass / low-mid / mid / high-mid / air, and the
                spectral rolloff (AI audio often has a hard lowpass around 16 kHz)
  stereo        width (side vs mid energy) and mono compatibility (phase correlation)
  groove        tempo, tempo stability between sections, kick regularity
  development   how much the sound changes over the track (a loop that never changes
                is boring; a track that changes constantly is not a focus track)
  cleanliness   clicks, hum/noise floor, near-silent stretches, clipping

Each metric gets 0-100 against targets for streaming-ready lounge deep house, and the
total is the weighted mean. Scores flag what to fix; they do not replace listening.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

BANDS = {
    "sub": (20, 60), "bass": (60, 250), "lowmid": (250, 500), "mid": (500, 2000),
    "highmid": (2000, 6000), "air": (6000, 16000),
}  # fmt: skip
# Typical share of energy (percent) for polished deep house; wide tolerance either side.
TARGET_SHARE = {
    "sub": (8, 30), "bass": (35, 65), "lowmid": (5, 14), "mid": (6, 20),
    "highmid": (1.5, 7), "air": (0.1, 1.5),
}  # fmt: skip


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def decode(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "a.wav"
        subprocess.run(
            [ffmpeg(), "-y", "-loglevel", "error", "-i", str(path), "-ar", "44100", "-ac", "2",
             str(wav)],
            check=True,
        )  # fmt: skip
        data, sr = sf.read(str(wav), always_2d=True, dtype="float32")
    return data, sr


def loudness(path: Path) -> dict:
    out = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
         "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr  # fmt: skip
    tail = out[out.rfind("Summary:") :]

    def grab(label: str) -> float:
        for line in tail.splitlines():
            if line.strip().startswith(label):
                return float(line.split(":")[1].split()[0])
        return float("nan")

    return {"lufs": grab("I:"), "lra": grab("LRA:"), "true_peak": grab("Peak:")}


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def band_report(mono: np.ndarray, sr: int) -> tuple[dict, float]:
    n = 1 << 15
    window = np.hanning(n)
    segs = mono[: len(mono) // n * n].reshape(-1, n) * window
    power = (np.abs(np.fft.rfft(segs, axis=1)) ** 2).mean(axis=0)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    total = power[(freqs >= 20) & (freqs <= 20000)].sum()
    shares = {}
    for name, (lo, hi) in BANDS.items():
        shares[name] = float(100 * power[(freqs >= lo) & (freqs < hi)].sum() / total)
    cum = np.cumsum(power[(freqs >= 20) & (freqs <= 22000)])
    f = freqs[(freqs >= 20) & (freqs <= 22000)]
    rolloff = float(f[np.searchsorted(cum, 0.999 * cum[-1])])
    return shares, rolloff


def tempo(mono: np.ndarray, sr: int) -> tuple[float, float]:
    """(bpm, stability): stability is 1 minus the spread of per-section tempi."""
    hop = 512
    fps = sr / hop

    def one(x: np.ndarray) -> float:
        n = len(x) // hop
        env = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
        on = np.maximum(0, np.diff(env))
        on = on - on.mean()
        ac = np.correlate(on, on, mode="full")[len(on) - 1 :]
        lags = np.arange(1, len(ac))
        bpm = 60 * fps / lags
        ok = (bpm >= 90) & (bpm <= 150)
        return float(bpm[ok][np.argmax(ac[1:][ok])])

    overall = one(mono)
    chunk = len(mono) // 4
    parts = [one(mono[i * chunk : (i + 1) * chunk]) for i in range(4)]
    spread = float(np.std([p if abs(p - overall) < overall * 0.3 else overall for p in parts]))
    return overall, clamp01(1 - spread / 6)


def development(mono: np.ndarray, sr: int) -> float:
    """Mean spectral distance between 4-second sections (0 = loop, higher = changes)."""
    n = sr * 4
    segs = mono[: len(mono) // n * n].reshape(-1, n)
    spec = np.array([np.log1p(np.abs(np.fft.rfft(s * np.hanning(n)))[: n // 8]) for s in segs])
    spec = spec / np.linalg.norm(spec, axis=1, keepdims=True)
    dist = 1 - spec @ spec.T
    return float(dist[np.triu_indices(len(dist), 1)].mean())


def analyze(path: Path) -> dict:
    data, sr = decode(path)
    mono = data.mean(axis=1)
    left, right = data[:, 0], data[:, 1]
    mid, side = (left + right) / 2, (left - right) / 2
    r: dict = {"file": path.name, "seconds": round(len(mono) / sr, 1)}
    r.update(loudness(path))
    shares, rolloff = band_report(mono, sr)
    r["shares"] = {k: round(v, 1) for k, v in shares.items()}
    r["rolloff_hz"] = round(rolloff)
    r["width"] = round(float(np.sqrt((side**2).mean() / max((mid**2).mean(), 1e-12))), 3)
    corr = np.corrcoef(left[: sr * 60], right[: sr * 60])[0, 1]
    r["phase_corr"] = round(float(corr), 3)
    bpm, stab = tempo(mono, sr)
    r["bpm"], r["tempo_stability"] = round(bpm, 1), round(stab, 3)
    r["development"] = round(development(mono, sr), 3)
    r["clicks_per_min"] = round(
        float((np.abs(np.diff(mono)) > 0.5).sum() / (len(mono) / sr / 60)), 2
    )
    hop = sr // 2
    rms = np.sqrt((mono[: len(mono) // hop * hop].reshape(-1, hop) ** 2).mean(axis=1))
    body = rms[4:-6]
    r["quiet_share"] = round(float((body < rms.max() * 0.08).mean()), 3)
    r["clip_share"] = round(float((np.abs(data) > 0.999).mean()), 5)
    r["dynamics_db"] = round(float(20 * np.log10(np.percentile(body, 95) / max(np.percentile(body, 5), 1e-9))), 1)
    return r


def score(r: dict) -> dict:
    s, notes = {}, []

    def put(name: str, value: float, why: str) -> None:
        s[name] = round(100 * clamp01(value))
        if value < 0.7:
            notes.append(why)

    put("loudness", 1 - abs(r["lufs"] + 14) / 4, f"loudness {r['lufs']} LUFS (target -14)")
    put("peak", clamp01((-0.9 - r["true_peak"]) / 0.9 + 1) if r["true_peak"] > -1 else 1,
        f"true peak {r['true_peak']} dBTP is above -1")
    bal = []
    for band, (lo, hi) in TARGET_SHARE.items():
        v = r["shares"][band]
        bal.append(1 - clamp01(max(lo - v, v - hi, 0) / max(hi - lo, 1) ))
    put("tonal_balance", float(np.mean(bal)), f"tonal balance off: {r['shares']}")
    put("brightness", clamp01((r["rolloff_hz"] - 9000) / 7000),
        f"hard lowpass near {r['rolloff_hz']} Hz (dull/AI-sounding top end)")
    put("stereo", 1 - abs(r["width"] - 0.3) / 0.5, f"stereo width {r['width']} (target ~0.2-0.5)")
    put("mono_compat", clamp01((r["phase_corr"] - 0.2) / 0.6),
        f"phase correlation {r['phase_corr']} (weak mono compatibility)")
    put("tempo_lock", r["tempo_stability"], f"tempo drifts between sections ({r['tempo_stability']})")
    put("development", 1 - abs(r["development"] - 0.12) / 0.15,
        f"development {r['development']} (too static or too restless; target ~0.05-0.2)")
    put("cleanliness", 1 - clamp01(r["clicks_per_min"] / 5) - clamp01(r["quiet_share"] / 0.1)
        - clamp01(r["clip_share"] / 0.002),
        f"artifacts: {r['clicks_per_min']} clicks/min, {r['quiet_share']:.0%} near-silent")
    put("dynamics", 1 - abs(r["dynamics_db"] - 9) / 12, f"dynamics {r['dynamics_db']} dB")
    weights = {"loudness": 1, "peak": 1, "tonal_balance": 2, "brightness": 2, "stereo": 1,
               "mono_compat": 1, "tempo_lock": 2, "development": 2, "cleanliness": 2,
               "dynamics": 1}  # fmt: skip
    total = sum(s[k] * w for k, w in weights.items()) / sum(weights.values())
    return {"scores": s, "total": round(total), "fix": notes}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+")
    p.add_argument("--csv", default="")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    rows = []
    for f in args.files:
        r = analyze(Path(f))
        r.update(score(r))
        rows.append(r)
        if args.json:
            print(json.dumps(r))
            continue
        print(f"\n{r['file']}  [{r['seconds']}s]  TOTAL {r['total']}/100")
        print(f"  loudness {r['lufs']} LUFS  LRA {r['lra']}  true peak {r['true_peak']} dBTP")
        print(f"  tempo {r['bpm']} bpm  stability {r['tempo_stability']}  development {r['development']}")
        print(f"  bands % {r['shares']}  rolloff {r['rolloff_hz']} Hz")
        print(f"  stereo width {r['width']}  phase {r['phase_corr']}  clicks/min {r['clicks_per_min']}")
        print("  scores:", ", ".join(f"{k} {v}" for k, v in r["scores"].items()))
        for n in r["fix"]:
            print("  ! ", n)
    if args.csv:
        flat = [{k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()} for r in rows]
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(flat[0]))
            w.writeheader()
            w.writerows(flat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
