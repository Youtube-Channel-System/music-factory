"""Generate original instrumental lounge deep house with ACE-Step 1.5 (MIT, runs on CPU).

Run inside an ACE-Step checkout (the workflow does this):

    python ../generate.py --out ../out --count 8 --seconds 170 --seed 123 \
        --shard 1 --run-seed 987 --catalog ../catalog/tracks.json

Sound target: smooth instrumental deep house / lounge for focus — warm basslines, soft
piano and Rhodes, subtle percussion, jazzy lounge textures, 118-124 BPM, around 2:50 per
track (the format of the big focus-house channels). Every track is new music made from a
text description, so it has no third-party owner.

Prompting follows the ACE-Step 1.5 guides: caption under 512 characters, 8-14 comma
separated tags with the genre first, concrete instruments, production tags, BPM in both
the tags and the `bpm` field, key in `keyscale`, lowercase section markers for structure,
and the planner LM kept from rewriting the caption so every track stays on-style.

Each take passes an automatic quality check (length, silence, clipping, steady low end,
tempo lock) and is mastered for streaming (-14 LUFS, -1 dBTP) before it is kept.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

GENERATOR = "music-factory v4"

# Sub-styles of the same sound (v4). Captions follow the ACE-Step 1.5 guide: genre first,
# then a session-musician description with concrete instruments, harmony, groove and mix.
# Research notes (deep house): 118-124 BPM, jazz voicings (minor 7ths and 9ths), Rhodes and
# piano, slow-attack pads, low-passed melodic bass, laid-back 909-style 4/4 drums, long
# builds and breakdowns. Owner's request: a light, distant muted trumpet on top.
TRUMPET = "a distant muted trumpet plays short soft phrases now and then"
STYLES: list[tuple[str, int, str]] = [
    ("lounge-piano", 4,
     "deep house, lounge, instrumental. Warm Rhodes and soft grand piano playing minor "
     "seventh and ninth chords, round low-passed bassline, laid-back 909 kick, crisp "
     "shuffled hi-hats, light shaker, " + TRUMPET + ". Elegant, smooth, late-night cocktail "
     "bar mood. Hi-fi studio mix, warm analog tape, wide stereo, clean low end, {bpm} bpm"),
    ("melodic-night", 3,
     "melodic deep house, instrumental. Felt piano melody over slow-attack analog pads, "
     "deep warm sub bass, soft claps, rolling percussion, " + TRUMPET + " in the breakdown. "
     "Cinematic, nocturnal, focused. Hi-fi mix, lush reverb, wide stereo, punchy but soft "
     "kick, {bpm} bpm"),
    ("jazzy-lounge", 4,
     "jazzy deep house, lounge, instrumental. Rhodes ninth chords, warm upright-style "
     "bassline, brushed hi-hats, soft kick, muted trumpet melody with gentle reverb, "
     "occasional vibraphone notes. Sophisticated hotel lobby mood, nu jazz feel. Hi-fi "
     "mix, subtle tape saturation, wide stereo, {bpm} bpm"),
    ("old-money-lounge", 4,
     "lounge house, deep house, instrumental. Soft grand piano voicings, jazzy Rhodes "
     "chords, round warm bassline, brushed hi-hats, gentle four-on-the-floor kick, "
     "light congas, " + TRUMPET + ". Refined, luxurious, old money, private members club. "
     "Polished hi-fi mix, subtle vinyl warmth, wide stereo, {bpm} bpm"),
    ("organic-guitar", 2,
     "organic deep house, soulful, instrumental. Nylon guitar licks, warm Rhodes chords, "
     "rolling bassline, congas and bongos, soft claps, " + TRUMPET + ". Sunset terrace "
     "mood, smooth and warm. Hi-fi mix, natural room reverb, wide stereo, {bpm} bpm"),
    ("hypnotic-focus", 1,
     "deep house, hypnotic, instrumental. Minimal piano stabs with seventh chords, warm "
     "analog bass, sidechained pads, tight hi-hats, soft kick, sparse muted trumpet echo. "
     "Focused, steady, deep work. Clean hi-fi mix, wide stereo, {bpm} bpm"),
    ("sax-sunset", 2,
     "soulful deep house, chill, instrumental. Smooth tenor saxophone phrases, lush Rhodes "
     "chords, warm bassline, crisp percussion, soft claps, a muted trumpet answers the sax "
     "once in a while. Golden hour, relaxed and classy. Hi-fi mix, wide stereo, {bpm} bpm"),
    ("boutique-deep", 4,
     "soulful deep house, boutique store, instrumental. Steady four-on-the-floor kick, "
     "dubby rolling bassline, warm Rhodes stabs with minor ninth chords, shakers and "
     "rimshots, smooth saxophone hook, " + TRUMPET + ". Classy, groovy, upscale fashion "
     "store. Hi-fi mix, deep spacious reverb, wide stereo, {bpm} bpm"),
]  # fmt: skip
STRUCTURES = [
    "[Intro - filtered Rhodes and soft kick]\n\n[Instrumental - full groove]\n\n"
    "[Breakdown - piano and pads, no kick]\n\n[Instrumental - groove returns with trumpet]"
    "\n\n[Outro - elements fade out]",
    "[Intro - percussion and bass]\n\n[Instrumental - chords enter]\n\n"
    "[Instrumental - melody on top]\n\n[Breakdown - soft pads]\n\n[Build-up]\n\n"
    "[Instrumental - full groove]\n\n[Outro]",
    "[Intro - soft pads]\n\n[Instrumental - deep groove]\n\n[Breakdown - trumpet solo "
    "over chords]\n\n[Instrumental - full groove]\n\n[Instrumental]\n\n[Outro]",
]
KEYS = ["A minor", "D minor", "E minor", "G minor", "C minor", "F minor", "B minor", "C major"]
BPMS = [118, 119, 120, 120, 121, 122, 122, 123]

# Mastering for streaming: clean sub, light glue, -14 LUFS integrated, -1 dBTP ceiling.
def master_chain(seconds: float) -> str:
    return (
        "highpass=f=30,equalizer=f=65:t=q:w=1.0:g=1.0,equalizer=f=11000:t=h:w=1:g=1.0,"
        "acompressor=threshold=-20dB:ratio=1.8:attack=30:release=250:makeup=1,"
        "loudnorm=I=-14:TP=-1.0:LRA=9,"
        f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, seconds - 4):.2f}:d=4"
    )


# Track names in the niche's voice: short, focused, original. Combined and de-duplicated
# against the catalog so no title ever repeats (streaming services flag duplicates).
WORDS_A = [
    "Quiet", "Deep", "Clean", "Late", "Early", "Silent", "Steady", "Golden", "Velvet", "Cold",
    "Black", "Private", "Corner", "Long", "Sharp", "Still", "Soft", "Midnight", "Morning",
    "Focused", "Patient", "Calm", "Slow", "Glass", "Marble", "Linen", "Cedar", "Amber",
    "Northern", "Hidden", "Second", "Final", "Open", "Higher", "Inner", "Lower", "Distant",
]  # fmt: skip
FOCUS_PHRASES = [
    "Deep Work Mode", "One More Hour", "Inbox Zero", "Do Not Disturb", "Head Down",
    "Execution Phase", "Quiet Hustle", "Compound Interest", "Office Hours", "After Hours",
    "Second Wind", "Final Draft", "Focus Window", "Single Task", "Clear Desk", "Night Shift",
    "Early Bird", "No Days Off", "Momentum", "Flow Session", "Locked", "Close The Tabs",
    "Build Mode", "Long Game", "Ship It", "Silent Grind", "Work In Silence", "Mind Over Noise",
    "Phone Face Down", "Deadline Tonight", "Last Revision", "Five More Pages", "Earned Not Given",
    "Discipline Daily", "Calm Ambition", "Cold Focus", "Steady Hands", "Brick By Brick",
    "Main Character Work", "The Long Way", "Patience Pays", "Quarter End", "Board Meeting",
    "Corner Office", "Study Hall", "Library Hours", "Exam Week", "Thesis Night", "Code Review",
    "Deploy Friday", "Pull Request", "Black Coffee", "Second Cup", "Morning Pages", "Sunday Reset",
    "Monday Plan", "Weekly Review", "Big Picture", "Fine Print", "Keep Going", "No Shortcuts",
    "Built Different", "Back To Work", "Stay Hungry", "Quiet Money", "Private Office",
    "Top Floor", "City Lights", "Midnight Oil", "Laser Focus", "Zero Distractions",
    "Momentum Builder", "Clear Mind", "Pure Flow", "Time Blocked", "Focus Protocol",
]  # fmt: skip
WORDS_B = [
    "Hours", "Desk", "Ledger", "Office", "Session", "Routine", "Ritual", "Margin", "Signal",
    "Rhythm", "Motion", "Current", "Draft", "Blueprint", "Notes", "Capital", "Compound",
    "Window", "Avenue", "Terrace", "Lobby", "Harbor", "Skyline", "Hallway", "Archive",
    "Studio", "Pattern", "Balance", "Horizon", "Tempo", "Method", "Practice", "Season",
    "Weekday", "Shift", "Room", "Mile", "Lane",
]  # fmt: skip


def title_pool(run_seed: int, taken: set[str]) -> list[str]:
    rng = random.Random(run_seed)
    combos = [f"{a} {b}" for a, b in itertools.product(WORDS_A, WORDS_B)]
    rng.shuffle(combos)
    phrases = FOCUS_PHRASES[:]
    rng.shuffle(phrases)
    # Interleave: searchable focus phrases (what the niche names its tracks) and the
    # channel's own quieter two-word titles.
    pool = [t for pair in itertools.zip_longest(phrases, combos) for t in pair if t]
    return [t for t in pool if t.casefold() not in taken]


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


def estimate_bpm(mono, sr: int) -> float:
    """Tempo from the autocorrelation of a simple onset envelope (90-150 BPM window)."""
    import numpy as np

    hop = 512
    n = len(mono) // hop
    frames = mono[: n * hop].reshape(n, hop)
    energy = np.sqrt((frames**2).mean(axis=1))
    onset = np.maximum(0, np.diff(energy))
    onset = onset - onset.mean()
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1 :]
    fps = sr / hop
    lags = np.arange(len(ac))
    bpm = np.where(lags > 0, 60 * fps / np.maximum(lags, 1), 0)
    window = (bpm >= 90) & (bpm <= 150)
    if not window.any():
        return 0.0
    best = lags[window][np.argmax(ac[window])]
    return float(60 * fps / best)


def quality(wav: Path, seconds: float, bpm: int) -> tuple[bool, str, dict]:
    """Reject takes with long silences, clipping, wrong length, no groove or a lost tempo."""
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(wav), always_2d=True)
    mono = data.mean(axis=1)
    stats: dict = {}
    if len(mono) < sr * seconds * 0.9:
        return False, f"too short ({len(mono) / sr:.0f}s)", stats
    peak = float(np.abs(mono).max())
    if peak < 1e-3:
        return False, "silent", stats
    clipped = float((np.abs(data) > 0.999).mean())
    if clipped > 0.002:
        return False, f"clipping {clipped:.2%}", stats
    hop = sr // 2
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames**2).mean(axis=1))
    body = rms[4:-6] if len(rms) > 12 else rms  # ignore intro/outro
    quiet = float((body < rms.max() * 0.08).mean())
    if quiet > 0.12:  # breakdowns are meant to be quiet; only long dead stretches fail
        return False, f"{quiet:.0%} near-silent", stats
    spec = np.abs(np.fft.rfft(frames[4:-6] if len(frames) > 12 else frames, axis=1))
    freqs = np.fft.rfftfreq(hop, 1 / sr)
    low = spec[:, (freqs > 40) & (freqs < 160)].mean(axis=1)
    if float((low < low.max() * 0.05).mean()) > 0.18:
        return False, "no steady kick/bass", stats
    found = estimate_bpm(mono, sr)
    ratio = found / bpm if bpm else 1
    locked = any(abs(ratio - r) < 0.08 for r in (0.5, 1.0, 2.0, 2 / 3, 1.5))
    stats = {"peak": round(peak, 2), "quiet": round(quiet, 3), "bpm_found": round(found, 1)}
    if not locked:
        return False, f"tempo drift (asked {bpm}, found {found:.0f})", stats
    return True, f"ok peak={peak:.2f} quiet={quiet:.0%} bpm~{found:.0f}", stats


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="out")
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--seconds", type=float, default=230)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument(
        "--budget-min", type=float, default=270, help="stop starting takes after this many minutes"
    )
    p.add_argument("--shard", type=int, default=1)
    p.add_argument("--run-seed", type=int, default=0, help="same for every shard of a run")
    p.add_argument("--catalog", default="", help="catalog/tracks.json, to keep titles unique")
    p.add_argument("--model", default="acestep-v15-xl-turbo", help="DiT checkpoint")
    p.add_argument("--lm", default="acestep-5Hz-lm-1.7B", help="planner LM, or 'none'")
    p.add_argument("--shift", type=float, default=3.0, help="timestep shift (guide: 3.0 for turbo)")
    p.add_argument("--steps", type=int, default=8, help="denoising steps (turbo: 8, max 20)")
    args = p.parse_args()

    sys.path.insert(0, str(Path.cwd()))
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    if args.catalog and Path(args.catalog).exists():
        taken = {t["title"].casefold() for t in json.loads(Path(args.catalog).read_text())}
    titles = title_pool(args.run_seed, taken)
    # Each shard takes its own slice of the shuffled pool: unique across the whole run.
    start = (args.shard - 1) * args.count
    titles = titles[start : start + args.count]

    t0 = time.time()
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(
        project_root=str(Path.cwd()), config_path=args.model, device="cpu"
    )
    print("dit init:", ok, msg, f"{time.time() - t0:.0f}s", flush=True)
    llm = LLMHandler()
    thinking = args.lm != "none"
    if thinking:
        t1 = time.time()
        llm.initialize(
            checkpoint_dir=str(Path.cwd() / "checkpoints"),
            lm_model_path=args.lm,
            backend="pt",
            device="cpu",
        )
        print("lm init:", llm.llm_initialized, f"{time.time() - t1:.0f}s", flush=True)
    rng = random.Random(args.seed)
    names = [s[0] for s in STYLES]
    weights = [s[1] for s in STYLES]
    manifest, rejected = [], 0
    started = time.time()
    manifest_path = out / f"tracks-{args.seed:05d}.json"
    for i in range(args.count):
        for attempt in range(args.retries + 1):
            if time.time() - started > args.budget_min * 60:
                print(f"time budget of {args.budget_min:.0f} min used: stopping early", flush=True)
                break
            style = rng.choices(names, weights=weights, k=1)[0]
            bpm = rng.choice(BPMS)
            key = rng.choice(KEYS)
            caption = dict((s[0], s[2]) for s in STYLES)[style].format(bpm=bpm)
            structure = rng.choice(STRUCTURES)
            seed = rng.randrange(1, 2**31 - 1)
            params = GenerationParams(
                caption=caption,
                lyrics=structure,
                instrumental=True,
                bpm=bpm,
                keyscale=key,
                timesignature="4",
                duration=args.seconds,
                shift=args.shift,
                inference_steps=args.steps,
                thinking=thinking,
                use_cot_caption=False,  # keep our caption: every track stays on-style
                use_cot_metas=False,  # BPM and key are ours too
                use_cot_language=False,
            )
            config = GenerationConfig(
                batch_size=1, audio_format="wav", use_random_seed=False, seeds=[seed]
            )
            t = time.time()
            result = generate_music(dit, llm, params, config, save_dir=str(out / "raw"))
            took = time.time() - t
            if not (result.success and result.audios):
                print(f"track {i} take {attempt}: failed {result.error}", flush=True)
                continue
            wav = to_wav(result.audios[0], out / f"take-{i}-{attempt}.wav")
            good, why, stats = quality(wav, args.seconds, bpm)
            print(f"track {i} take {attempt} [{style}]: {why} ({took:.0f}s)", flush=True)
            if not good:
                rejected += 1
                wav.unlink(missing_ok=True)
                continue
            name = f"fc4-{args.seed:05d}-{i:02d}.mp3"
            subprocess.run(
                [ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav),
                 "-af", master_chain(args.seconds), "-ar", "44100", "-b:a", "320k",
                 str(out / name)],
                check=True,
            )  # fmt: skip
            wav.unlink(missing_ok=True)
            try:  # objective scorecard goes into the catalog (see analyze.py); never blocks
                import analyze

                rep = analyze.analyze(out / name)
                rep.update(analyze.score(rep))
                stats.update(
                    score=rep["total"], lufs=rep["lufs"], true_peak=rep["true_peak"],
                    rolloff_hz=rep["rolloff_hz"], dynamics_db=rep["dynamics_db"],
                )  # fmt: skip
                print(f"track {i} scorecard {rep['total']}/100", flush=True)
            except Exception as e:  # analysis is advisory
                print(f"track {i} scorecard skipped: {e}", flush=True)
            manifest.append(
                {
                    "file": name,
                    "title": titles[i] if i < len(titles) else f"Session {args.seed}-{i}",
                    "creator": "FOCUS & CO",
                    "license": "original",
                    "duration_s": args.seconds,
                    "tags": ["deep house", "lounge", "instrumental", f"{bpm} bpm", key],
                    "bpm": bpm,
                    "key": key,
                    "style": style,
                    "caption": caption,
                    "structure": structure.replace("\n\n", " "),
                    "seed": seed,
                    "model": args.model,
                    "lm": args.lm,
                    "generator": GENERATOR,
                    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "qa": stats,
                }
            )
            manifest_path.write_text(json.dumps(manifest, indent=2))  # survives a cancelled job
            break
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"kept {len(manifest)}/{args.count}, rejected takes {rejected}", flush=True)
    return 0 if manifest else 1


if __name__ == "__main__":
    raise SystemExit(main())
