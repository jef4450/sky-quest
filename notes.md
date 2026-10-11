# Sky Quest — Setup Notes

## Local AI timing test

- Model: `gemma3:1b`
- Test prompt: "2 friendly sentences about spotting Jupiter"
- Time taken: \_\_\_ seconds
- Output notes: \_\_\_

## Setup checklist

- [ ] Public GitHub repository created during the challenge
- [x] Project files created
- [ ] Ollama model downloaded and tested
- [ ] Python dependencies installed
- [ ] Day 1 tests verified

- Time taken: 5–10 seconds
- Output notes: Good — two friendly sentences, but it didn't mention Jupiter's location or visibility facts.

## Sky Quest Validation — October 11, 2026

### Planet and Moon Position Checks

Compared Sky Quest's calculated positions with Stellarium at approximately 9:46 PM IST on October 11, 2026, for the Nagercoil area.

| Object  | Sky Quest Altitude | Stellarium Altitude | Difference |
| ------- | -----------------: | ------------------: | ---------: |
| Saturn  |             +62.1° |              +60.0° |       2.1° |
| Jupiter |             -59.8° |              -61.0° |       1.2° |
| Moon    |             -47.8° |              -45.9° |       1.9° |

The directions and above/below-horizon status agreed for all three objects. These comparisons suggest that the position calculations are reasonably close to Stellarium.

### ISS Pass Check

Compared Sky Quest's prediction with Heavens-Above for October 12, 2026.

| Measurement      | Sky Quest    | Heavens-Above                                                   |
| ---------------- | ------------ | --------------------------------------------------------------- |
| Pass time        | 04:21 AM IST | 04:21:05 AM IST                                                 |
| Maximum altitude | 23.7°        | 24°                                                             |
| Duration         | 4.5 minutes  | Approximately 2 minutes 11 seconds between listed start and end |

The predicted time and maximum altitude were very close. The duration differed and needs further investigation. Heavens-Above was configured for Marthandam, rather than the exact Nagercoil coordinates, so the comparison was approximate.

### Local Gemma Test

Model: `gemma3:1b` via Ollama.

Test prompt: "2 friendly sentences about spotting Jupiter"

The model generated two friendly sentences about observing Jupiter. Response time was not measured.

During the application run, the grounding checker rejected two generated responses and the application fell back to a fact-only template. This demonstrated that the fallback behavior was working, although the grounding checker and generated wording may need improvement.
