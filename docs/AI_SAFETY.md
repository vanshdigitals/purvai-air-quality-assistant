# AI Behaviour and Safety (owner of AI rules)

**SAF-01:** the deterministic rules engine decides the safety verdict. AI only explains and personalises. AI cannot downgrade or override a warning, compute AQI, diagnose or invent data.

System instructions: plain words; use supplied context only; cite fields; say "I don't have that data" when missing; never contradict `verdict.level`.

SAF-02 grounding: each call has AQI, category, source label, time and verdict. Modelled data must be called "modelled estimate". Stale data must state its age.
SAF-03 no diagnosis, medicine, dosage, cures, or claims that masks or purifiers make air "safe".
SAF-04 respiratory or chest symptoms set `needs_doctor_note=true`; UI adds "Consult a doctor".
SAF-05 sensitive groups get stricter wording. Masks: well-fitted N95/FFP2; BIS IS 9473 marking unverified, so no standard number is claimed.

## Guard and contradictions
Server checks after Pydantic validation:
1. `verdict_level` equals the rules household level (`GUARD_VERDICT`).
2. `action_id`s belong to `context.verdict.action_ids` (for `DailyPlanWording`, each period's `action_id`s match that period's rules exactly; for `IndoorAdvice`, `tip_id`s belong to the level's rule tips).
3. Banned-claim check (case-insensitive whole words or phrases across all text fields, `GUARD_BANNED_CLAIM`): words `cure`, `cures`, `cured`, `dosage`, `dose`, `mg`, `prescribe`, `prescription`, `diagnose`, `diagnosis`; phrases `makes the air safe`, `make the air safe`, `air is safe`, `completely safe`, `100% safe`, `fully protects`, `guaranteed`.
4. Permissive phrases rejected when household level is `poor`, `very_poor`, or `severe` (`GUARD_PERMISSIVE`): `safe to go out`, `safe to play outside`, `fine to go out`, `okay to go out`, `ok to go out`, `no need for a mask`, `no mask needed`, unless negated by one of `not`, `no`, `never`, `isn't`, `is not`, `aren't`, `don't`, `do not`, `avoid`, or `unsafe` within the 4 words before the phrase.
5. Number and time grounding: every numeric value in text fields must lie within ±1 of a number in `context` (`GUARD_NUMBER`), skipping pollutant names (`PM2.5`, `PM10`, `NO2`, `SO2`, `O3`, `CO`, `CO2`), mask labels (`N95`, `FFP2`), and the GRAP stage; clock expressions (`5 pm`, `5pm`, `5 PM`, `5:00 pm`, `17:00`, `17.00`, `5:30 pm`, `17:30`) and ranges (`4 to 6 pm`, checking both ends) are normalised to 24 h `HH:MM` and checked against `local_time`, `observed_time_ist`, `forecast` times (within ±30 minutes for Open-Meteo `:30` IST forecast hours), or times present in the user message (`GUARD_TIME`). Durations (`2 hours`, `30 minutes`) are not clock times: age durations (`X minutes old`, `X hours ago`) are checked against `age_minutes` / `age_hours`, while general-advice durations (`for 30 minutes`, `every 2 hours`) are skipped.
6. Length caps enforced by schemas (`extra="forbid"`). Any failure discards the reply; fallback once, then template.

## Symptom keywords (SAF-04)
Server enforces `needs_doctor_note=true` and `out_of_scope=false` (symptoms are in scope, also on templates; never cleared by AI) on: `cough`, `coughing`, `wheeze`, `wheezing`, `breathless`, `breathlessness`, `short of breath`, `shortness of breath`, `chest pain`, `chest tightness`, `can't breathe`, `cannot breathe`, `difficulty breathing`, `asthma attack`, `saans`.

## Prompt injection
User text is delimited as untrusted; embedded instructions are ignored. JSON-only output, no tools, immutable verdict, 500-char cap, control characters stripped.

## Failure and fallback
Gemini (15 s), Groq once, then a rule-catalogue template with `generated_by:"template"` and the note "AI unavailable, showing standard advice".

## Privacy and transparency
Derived context only. Gemini's unpaid tier allows human review, so no names, addresses, exact coordinates or past chat are sent (A-03). Prompts are never logged. Every answer shows source chips and a Rule or AI wording tag.
