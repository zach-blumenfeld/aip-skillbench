# Tuning notes — `process_video.py`

Load this reference if the first run of `process_video.py` produces a report
whose `compression_percentage` or `segments_removed` looks off (too aggressive,
too lenient, or has obviously wrong intervals).

## Silence threshold

`silencedetect=noise=<X>dB:d=<min_dur>` is the audio gate. ffmpeg measures the
audio level in dBFS; quieter than `<X>dB` for `<min_dur>` seconds counts as
silence.

| Symptom in output | Fix |
| --- | --- |
| Almost nothing was removed, but you can hear long pauses in the original. | The room tone is louder than `-30dB`. Try `--silence-db -25dB`, then `-20dB`. |
| Teaching content got cut — the report removes mid-sentence intervals. | Voice is dipping below the threshold. Try `--silence-db -35dB` or `-40dB`. |
| Many tiny < 2s gaps were left in. | The instruction says "usually > 2 sec", but you can lower `--silence-min` to e.g. `1.5` if the report under-shoots. |

Reasonable sweep order: `-30dB → -35dB → -25dB → -40dB → -20dB`.

## Opening freeze

The opening detector uses `freezedetect=n=<noise>:d=<dur>`. `n` is the
per-pixel tolerance — smaller `n` means stricter "must be identical". Default
`0.003` tolerates very faint analog noise on an otherwise still title card.

| Symptom | Fix |
| --- | --- |
| Opening was not detected (still in the output). | Try `--freeze-noise 0.01` to allow more noise, or `--freeze-min 0.5` to allow shorter openings. |
| Opening detector ate teaching content. | Tighten with `--freeze-noise 0.001`, or just `--skip-opening` and rely on silence detection alone. |
| Opening is animated/visually moving but silent. | Freeze detection won't fire. Silence detection will catch it if audio is quiet — bump `--silence-db` up (toward 0). |

The detector only considers freezes that begin within 1.0s of t=0. A static
slide later in the lecture is preserved.

## Math consistency

The evaluator checks `original ≈ compressed + removed`. The script computes
`removed = original - compressed` from `ffprobe` of the actual outputs, so the
identity holds by construction even after re-encoding rounding. Do not edit
the report by hand — re-run the script.

## Empty / near-empty output

If every interval ends up in `removes`, the script exits before writing an
empty video. That almost always means `--silence-db` is far too lenient
(e.g. `0dB`). Drop it back toward `-30dB`.

## Diagnostic dry run

Pass `--verbose` to print the detected intervals to stderr without changing
behavior. Useful to confirm whether the issue is detection or cutting before
re-encoding again.

## ffmpeg availability

The script shells out to `ffmpeg` and `ffprobe`. If either is missing:

```bash
which ffmpeg ffprobe
# macOS:  brew install ffmpeg
# Debian: apt-get install -y ffmpeg
```
