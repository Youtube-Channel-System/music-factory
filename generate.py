"""Generate original instrumental deep house with ACE-Step 1.5 (MIT, runs on CPU).

Run inside an ACE-Step checkout (the workflow does this):

    python ../generate.py --out ../out --count 10 --seconds 210 --seed 123

Every track is new music made by the model from a text description, so it has
no third-party owner and cannot trigger a Content ID claim from another catalog.
Each track passes an automatic quality check before it is kept; a failed take is
generated again with a new seed (up to --retries times).
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

# FOCUS & CO sound: smooth deep house built around warm Rhodes chords.
# One house style, several arrangements, so a one-hour mix stays coherent but never loops.
BASE = (
    "smooth instrumental deep house, warm Rhodes electric piano chords, soft four-on-the-floor "
    "kick, shuffled hi-hats, round deep sub bass, mellow lounge atmosphere, polished modern "
    "production, wide stereo, focus music, no vocals"
)
VARIATIONS = [
    "late night rooftop bar feel, subtle vinyl warmth",
    "airy pads underneath, gentle filter sweeps, steady and hypnotic",
    "jazzy seventh chords, light shaker groove, relaxed but driving",
    "deep plucked bass, soft clap on two and four, classy and minimal",
    "warm analog pad swells, slow chord progression, calm confidence",
    "muted guitar chops in the background, sunset terrace mood",
    "soft piano melody doubling the Rhodes, elegant and focused",
    "rolling bassline, crisp open hi-hats, smooth momentum for deep work",
]
KEYS = ["A minor", "D minor", "F minor", "G minor", "C minor", "E minor", "B minor", "Eb major"]
BPMS = [118, 120, 120, 122, 122, 124]

# Track names in the niche's voice: short, motivational, all original.
TITLE_A = [
    "Black Coffee", "Quiet Money", "Late Ledger", "Silent Hours", "Cold Brew", "Night Shift",
    "First Light", "Clean Desk", "Long Game", "Deep Work", "Sharp Suit", "Private Office",
    "Corner Office", "Old Money", "Market Close", "Early Hours", "Glass Tower", "Low Light",
    "Wall Street", "Penthouse", "Velvet Hours", "Closed Doors", "Gold Standard", "Midnight Desk",
]  # fmt: skip
TITLE_B = [
    "& Big Plans", "Mode", "Discipline", "No Excuses", "in Silence", "Momentum", "Ritual",
    "Session", "Hours", "Standards", "Focus", "Routine", "Ambition", "Composure", "Protocol",
    "Theory", "Mindset", "Rules",
]  # fmt: skip


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(audio: dict, dest: Path) -> Path:
    src = Path(audio["path"]) if audio.get("path") else None
    if src is not None and src.exists():
        return src
    import soundfile as sf

    tensor = audio["tensor"].float().cpu().numpy()  # [channels, samples]
    sf.write(str(dest), tensor.T, int(audio.get("sample_rate") or 48000))
    return dest


def quality(wav: Path, seconds: float) -> tuple[bool, str]:
    """Reject takes with long silences, clipping, wrong length or no steady beat."""
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(wav), always_2d=True)
    mono = data.mean(axis=1)
    if len(mono) < sr * seconds * 0.9:
        return False, f"too short ({len(mono) / sr:.0f}s)"
    peak = float(np.abs(mono).max())
    if peak < 1e-3:
        return False, "silent"
    clipped = float((np.abs(data) > 0.999).mean())
    if clipped > 0.002:
        return False, f"clipping {clipped:.2%}"
    hop = sr // 2
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames**2).mean(axis=1))
    loud = rms.max()
    body = rms[2:-2] if len(rms) > 6 else rms  # ignore intro/outro fades
    quiet = float((body < loud * 0.08).mean())
    if quiet > 0.08:
        return False, f"{quiet:.0%} near-silent"
    # A house groove keeps the low end busy: compare bass energy across the body.
    spec = np.abs(np.fft.rfft(frames[2:-2] if len(frames) > 6 else frames, axis=1))
    freqs = np.fft.rfftfreq(hop, 1 / sr)
    low = spec[:, (freqs > 40) & (freqs < 160)].mean(axis=1)
    if float((low < low.max() * 0.05).mean()) > 0.15:
        return False, "no steady kick/bass"
    return True, f"ok peak={peak:.2f} quiet={quiet:.0%}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="out")
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--seconds", type=float, default=210)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--thinking", action="store_true", help="also run the 0.6B planner LM")
    args = p.parse_args()

    sys.path.insert(0, str(Path.cwd()))
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(
        project_root=str(Path.cwd()), config_path="acestep-v15-turbo", device="cpu"
    )
    print("dit init:", ok, msg, f"{time.time() - t0:.0f}s", flush=True)
    llm = LLMHandler()
    if args.thinking:
        llm.initialize(
            checkpoint_dir=str(Path.cwd() / "checkpoints"),
            lm_model_path="acestep-5Hz-lm-0.6B",
            backend="pt",
            device="cpu",
        )
    rng = random.Random(args.seed)
    manifest, rejected = [], 0
    for i in range(args.count):
        for attempt in range(args.retries + 1):
            caption = f"{BASE}, {rng.choice(VARIATIONS)}"
            params = GenerationParams(
                caption=caption,
                lyrics="[Instrumental]",
                instrumental=True,
                bpm=rng.choice(BPMS),
                keyscale=rng.choice(KEYS),
                timesignature="4",
                duration=args.seconds,
                thinking=args.thinking,
            )
            config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=True)
            t = time.time()
            result = generate_music(dit, llm, params, config, save_dir=str(out / "raw"))
            took = time.time() - t
            if not (result.success and result.audios):
                print(f"track {i} take {attempt}: failed {result.error}", flush=True)
                continue
            wav = to_wav(result.audios[0], out / f"take-{i}-{attempt}.wav")
            good, why = quality(wav, args.seconds)
            print(f"track {i} take {attempt}: {why} ({took:.0f}s)", flush=True)
            if not good:
                rejected += 1
                wav.unlink(missing_ok=True)
                continue
            name = f"fc-{args.seed:05d}-{i:02d}.mp3"
            subprocess.run(
                [ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav),
                 "-af", "afade=t=in:d=1", "-b:a", "320k", str(out / name)],
                check=True,
            )  # fmt: skip
            wav.unlink(missing_ok=True)
            manifest.append(
                {
                    "file": name,
                    "title": f"{rng.choice(TITLE_A)} {rng.choice(TITLE_B)}",
                    "creator": "FOCUS & CO",
                    "license": "original",
                    "duration_s": args.seconds,
                    "tags": ["deep house", "rhodes", "instrumental", f"{params.bpm} bpm",
                             params.keyscale],
                }
            )  # fmt: skip
            break
    (out / f"tracks-{args.seed:05d}.json").write_text(json.dumps(manifest, indent=2))
    print(f"kept {len(manifest)}/{args.count}, rejected takes {rejected}", flush=True)
    return 0 if manifest else 1


if __name__ == "__main__":
    raise SystemExit(main())
