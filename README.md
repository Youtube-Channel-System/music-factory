# music-factory

Original instrumental deep house for **FOCUS & CO** ([@focusndco](https://www.youtube.com/@focusndco)).

The `generate` workflow runs [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (MIT license) on GitHub's CPU runners, writes smooth Rhodes-led deep house at 118–124 BPM, checks every take automatically (length, silence, clipping, steady low end) and adds the tracks that pass to the [`library`](../../releases/tag/library) release. The channel's daily pipeline ([channel-engine](https://github.com/Youtube-Channel-System/channel-engine), private) downloads that release and builds each one-hour mix from it.

- **Run it:** Actions → `generate` → Run workflow (parallel jobs × tracks per job). It also runs every Monday and adds about 30 tracks.
- **Cost:** none. This repository is public so its Actions minutes are free and unlimited.
- **Rights:** the music is generated from text descriptions, so it is original and owned by the channel. No samples or third-party recordings are used.

- **Lab mode:** run `generate` with `publish=false` to compare settings (model, LM) without touching the library; each shard pushes a `lab-<run>-<shard>` branch with its MP3 for you to listen to.
- **Policies:** [Privacy](PRIVACY.md) and [Terms](TERMS.md) for the channel's OAuth consent screen.

| File | Purpose |
|---|---|
| `generate.py` | Prompt bank, generation loop, quality check, MP3 export and track titles. |
| `.github/workflows/generate.yml` | Installs ACE-Step for CPU and runs `generate.py` in parallel jobs. |

## Sound target and catalog (v3)

Smooth instrumental deep house / lounge for focus: warm basslines, soft piano and Rhodes, subtle percussion, jazzy lounge textures, 118–124 BPM, about 2:50 per track. `generate.py` holds six sub-styles written as ACE-Step tag lists (genre first, concrete instruments, production tags, BPM in tags and in `bpm`, key in `keyscale`, lowercase structure markers) and keeps the planner LM from rewriting them. Takes are rejected for silence, clipping, no steady low end or a lost tempo, then mastered to −14 LUFS / −1 dBTP for streaming.

`catalog/tracks.csv` and `catalog/tracks.json` list every track (title, BPM, key, length, prompt, seed, QA stats) with empty release columns (`isrc`, `release_date`, `album`…) for when you distribute to Spotify. The workflow refreshes it after each publishing run.

---
FOCUS & CO engine uses YouTube API Services to upload the owner's own videos to the owner's own YouTube channel.
[Privacy Policy](PRIVACY.md) · [Terms of Service](TERMS.md) · [YouTube Terms of Service](https://www.youtube.com/t/terms) · [Google Privacy Policy](https://policies.google.com/privacy)
