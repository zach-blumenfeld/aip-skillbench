# ffmpeg detection reference

Load this when detection results look wrong — too much or too little removed,
the opening not caught, or speech clipped. It explains the two ffmpeg filters
the scripts drive and how to tune them.

## Why two detectors

The opening and the pauses are different signals and need different filters:

| Removable content | Audio | Video | Detector |
|-------------------|-------|-------|----------|
| Opening title / leader | non-speech (hum, noise, music) | **static / frozen frame** | `freezedetect` |
| Long teaching pause | **silent** | usually live | `silencedetect` |

`silencedetect` will **miss the opening** because the opening usually has
audio noise (it is not silent). `freezedetect` catches it because the frame is
static. Run both; never rely on silence alone for the opening.

## silencedetect

```
ffmpeg -i input.mp4 -af silencedetect=noise=-30dB:d=2 -f null -
```
Logs to **stderr**:
```
[silencedetect @ ...] silence_start: 12.34
[silencedetect @ ...] silence_end: 15.67 | silence_duration: 3.33
```
- `noise` — anything quieter than this is "silent". `-30dB` is a good start.
  Make it **less negative** (`-25dB`) if real pauses are missed because of
  background hum; **more negative** (`-40dB`) if quiet speech is being cut.
- `d` — minimum pause length. The task removes pauses **> 2s**, so `d=2`.
- A trailing `silence_start` with no matching `silence_end` means the clip ends
  while silent; close it at the probed duration (the script does this).

## freezedetect

```
ffmpeg -i input.mp4 -vf freezedetect=n=-60dB:d=2 -map 0:v:0 -f null -
```
Logs to **stderr**:
```
[freezedetect @ ...] lavfi.freezedetect.freeze_start: 0
[freezedetect @ ...] lavfi.freezedetect.freeze_duration: 6.5
[freezedetect @ ...] lavfi.freezedetect.freeze_end: 6.5
```
- `n` — per-pixel noise tolerance. `-60dB` treats near-identical frames as
  frozen. Raise toward `-50dB`/`-45dB` if the opening has light noise/dithering
  over an otherwise static frame and is not detected.
- `d` — minimum frozen duration.
- **Only the leading freeze is the opening.** A presenter holding still mid-
  lecture also freezes; `detect_segments.py` keeps those by accepting a freeze
  as the opening only when it starts within `--opening-max-start` seconds.

## Tuning loop

1. Run `detect_segments.py`, read the printed preview compression %.
2. Sanity-check the plan in `analysis.json` against expectations:
   - opening removed (a removal segment with `"reason": "opening"` starting at 0),
   - pauses > 2s removed,
   - kept segments cover the bulk of the runtime (teaching content preserved).
3. A teaching video typically compresses **~5–35%**. Far outside that band
   usually means a threshold is off:
   - **Too little removed / opening missed** → raise `--freeze-noise-db`
     (e.g. `-50`), lower `--min-silence` slightly, or raise `--silence-noise-db`.
   - **Too much removed / speech clipped** → lower `--silence-noise-db`
     (e.g. `-40`), raise `--min-silence`, or increase `--keep-pad`.
4. Re-run and re-check. Only proceed to `build_output.py` when the plan looks right.

## Fallbacks

- **Opening is visual noise (TV-static "snow"), not a frozen frame.**
  `freezedetect` won't fire (every frame differs). Detect the opening as the
  region before the first sustained speech instead: the first `silence_end`
  after t=0 often marks where teaching begins; remove `[0, that time]`. Or use
  scene detection: `ffmpeg -i in.mp4 -vf "select='gt(scene,0.4)',metadata=print" -f null -`.
- **No audio stream.** `detect_segments.py` skips silence detection and relies
  on freeze detection only.
- **Cutting is slightly off keyframe.** The render uses the `trim`/`atrim` +
  `concat` filter graph and re-encodes, so cuts are frame-accurate (not
  keyframe-snapped). This is why `build_output.py` re-encodes rather than doing
  a stream-copy `-c copy`.
