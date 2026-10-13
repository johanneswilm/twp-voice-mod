# Piper voice model quality notes (German / Spanish)

Measurements taken while casting 47 game characters for the voice mod, so
that you don't have to repeat our trial-and-error. All numbers were measured
on our pipeline; your mileage with different post-processing may vary slightly,
but the model-level verdicts held up across thousands of clips.

## Methodology

- **Pitch (f0)**: median autocorrelation-based f0 over voiced frames of a
  fixed test sentence (see `f0.py` in this repo). Used for gender matching —
  ~165 Hz is the natural male/female boundary for these models.
- **Intelligibility**: synthesized 8 fixed sentences per voice config,
  transcribed them with `faster-whisper` (base, int8) and scored character
  similarity against the source text. Reference values: the best voices score
  **0.86–1.00**; scores below ~0.7 mean the voice produces mumbly, slurred or
  stuttering output on many sentences.

## AVOID

| Model | Language | Problem |
|---|---|---|
| **`de_DE-mls-medium`** (all 236 speakers) | de | **Garbles badly.** ASR similarity 0.25–0.67 (vs 0.86–1.00 for all other German voices): mumbly delivery, intermittent stuttering and sound artifacts on a large fraction of sentences, worst on deep speakers. Verified across ~10,000 generated clips and 47 characters. Intelligible lines are mixed with unintelligible ones *within the same speaker*, which makes it especially frustrating. |
| **`es_ES-carlfm-x_low`** | es | x_low quality tier; noticeably robotic. |
| **`de_DE-eva_k-x_low`** | de | x_low quality tier; noticeably robotic. |

## Spanish — measured f0 vs. advertised gender (attention!)

Several "male" Spanish voices **sound female** — trust your ears or measure:

| Model | Advertised | Sounds like | Measured f0 |
|---|---|---|---|
| `es_AR-daniela-high` | female | female | 185 Hz |
| `es_MX-claude-high` | male | **female** | 176 Hz |
| `es_ES-davefx-medium` | male | male | 122 Hz |
| `es_MX-ald-medium` | male | male | 158 Hz |
| `es_ES-sharvard-medium` speaker 0 | male | male | 124 Hz |
| `es_ES-sharvard-medium` speaker 1 | female | female | 204 Hz |
| `es_ES-mls_10246-low` | male | **female** | 199 Hz |
| `es_ES-mls_9972-low` | male | **female** | 182 Hz |

Recommended Spanish casting pool: **davefx, ald, sharvard#0** for male
characters (only 3 solid male voices — differentiate with ±8–12% pitch
variants); **daniela, sharvard#1, claude, mls_10246, mls_9972** for female
characters (5 voices).

## German — recommended voices (all score ≥ 0.83)

| Model | Sounds like | f0 | Intelligibility |
|---|---|---|---|
| `de_DE-thorsten-high` | male | 137 Hz | 0.91–0.97 — best male voice |
| `de_DE-thorsten-medium` | male | 128 Hz | 0.86–1.00 (0.86–0.93 at pitch ≤ 0.9) |
| `de_DE-pavoque-low` | male | 128 Hz | 0.86–0.93 |
| `de_DE-karlsson-low` | male, very deep | 98 Hz | 0.90–0.97 |
| `de_DE-thorsten_emotional-medium` speaker 2 | female | 171 Hz | 0.96 |
| `de_DE-thorsten_emotional-medium` speaker 4 | male | 128 Hz | 0.94 |
| `de_DE-thorsten_emotional-medium` speaker 3 | male | 147 Hz | 0.91 |
| `de_DE-thorsten_emotional-medium` speaker 1 | female | 232 Hz | 0.86 |
| `de_DE-thorsten_emotional-medium` speaker 6 | male | 131 Hz | 0.85 |
| `de_DE-thorsten_emotional-medium` speaker 0 | male | 163 Hz | 0.84 |
| `de_DE-thorsten_emotional-medium` speaker 5 | male | 140 Hz | 0.81 |
| `de_DE-kerstin-low` | female | 173 Hz | 0.83–0.86 |
| `de_DE-ramona-low` | female | 216 Hz | 0.73–0.80 (use sparingly) |
| `de_DE-thorsten_emotional-medium` speaker 7 | female | 169 Hz | 0.73 (use sparingly) |

`de_DE-mls-medium` speaker f0 reference (for gender if you must use it):
male speakers 0–3, 6–13, 16, 18, 20–25, 27, 29, 32, 34, 39; female speakers
2, 4, 5, 10, 12, 14, 15, 17, 19, 26, 28, 30–31, 33, 35–38.

## Pitch shifting

`ffmpeg -af rubberband=pitch=X` (X = 0.5–2.0 scale factor) holds duration
constant and survives OGG re-encoding fine. Guidelines from casting 47
characters:

- Keep effective pitch within **±12%** of the model's natural f0 for natural
  results; shifts beyond ~20% start sounding artificial.
- For gender-crossing shifts (e.g. male voice +8–15% for a boy character)
  combine with a slight speed change (`length_scale` 0.92–1.08 in Piper) so
  characters stay distinguishable.
- Test the *effective* result: synthesize a fixed sentence, measure f0, and
  aim for 95–155 Hz (male) / 176–255 Hz (female).

## Quality-audit any voice yourself

The `asr_sweep.py` / `synth_audit.py` pattern from this repo works for any
Piper model: synthesize a dozen fixed sentences, transcribe with
faster-whisper, score similarity against the source text. Clean voices score
0.86+; anything below ~0.7 will read as "stuttering and sound errors" to
listeners — exactly the symptom that cost us two debugging rounds.