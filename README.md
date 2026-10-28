# music-factory

Original instrumental deep house for **FOCUS & CO** ([@focusndco](https://www.youtube.com/@focusndco)).

The `generate` workflow runs [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (MIT license) on GitHub's CPU runners, writes smooth Rhodes-led deep house at 118–124 BPM, checks every take automatically (length, silence, clipping, steady low end) and adds the tracks that pass to the [`library`](../../releases/tag/library) release. The channel's daily pipeline ([channel-engine](https://github.com/Youtube-Channel-System/channel-engine), private) downloads that release and builds each one-hour mix from it.

- **Run it:** Actions → `generate` → Run workflow (parallel jobs × tracks per job). It also runs every Monday and adds about 30 tracks.
- **Cost:** none. This repository is public so its Actions minutes are free and unlimited.
- **Rights:** the music is generated from text descriptions, so it is original and owned by the channel. No samples or third-party recordings are used.

| File | Purpose |
|---|---|
| `generate.py` | Prompt bank, generation loop, quality check, MP3 export and track titles. |
| `.github/workflows/generate.yml` | Installs ACE-Step for CPU and runs `generate.py` in parallel jobs. |
