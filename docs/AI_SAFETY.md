# AI Behaviour and Safety (owner of AI rules)

**SAF-01:** the deterministic rules engine decides the safety verdict. AI only explains and personalises. AI cannot downgrade or override a warning, compute AQI, diagnose or invent data.

System instructions: plain words; use supplied context only; cite fields; say "I don't have that data" when missing; never contradict `verdict.level`.

SAF-02 grounding: each call has AQI, category, source label, time and verdict. Modelled data must be called "modelled estimate". Stale data must state its age.
SAF-03 no diagnosis, medicine, dosage, cures, or claims that masks or purifiers make air "safe".
SAF-04 respiratory or chest symptoms set `needs_doctor_note=true`; UI adds "Consult a doctor".
SAF-05 sensitive groups get stricter wording. Masks: well-fitted N95/FFP2; BIS IS 9473 marking unverified, so no standard number is claimed.

## Guard and contradictions
Server checks after Pydantic validation (run on NFKC-normalised, zero-width-stripped, whitespace-collapsed, lower-cased text):
1. `verdict_level` equals the rules household level (`GUARD_VERDICT`).
2. `action_id`s belong to `context.verdict.action_ids` (for `DailyPlanWording`, each period's `action_id`s match that period's rules exactly; for `IndoorAdvice`, `tip_id`s belong to the level's rule tips).
3. Banned-claim and medicine-advice check (`GUARD_BANNED_CLAIM`): words `cure`, `cures`, `cured`, `dosage`, `dose`, `mg`, `prescribe`, `prescription`, `diagnose`, `diagnosis`, plus drug names (`paracetamol`, `antihistamine`, `antibiotic`, `steroid`, `salbutamol`, `montelukast`, `cetirizine`), dose-unit quantities (`\d+(\.\d+)?\s*(mg|ml|mcg|g\b|puffs?)`), instruction patterns (`take|give|use|start|increase|double` within 4 words of `medicine|medication|tablet|inhaler|dose|puff|syrup`), and phrases `makes the air safe`, `make the air safe`, `air is safe`, `completely safe`, `100% safe`, `fully protects`, `guaranteed`. Plain doctor mentions ("talk to a doctor about medicine") stay allowed.
4. Permissive patterns rejected when household level is `poor`, `very_poor`, or `severe` (`GUARD_PERMISSIVE`): `(safe|fine|ok|okay|alright) (for \w+ )?to (go|play|step|walk|run|exercise) out(side|doors)?`, `(can|may) (go|play|walk|run|exercise) out(side|doors)?` (when the same sentence has none of `if`, `only`, `must`, `need to`, `briefly`, `short`, `mask`, `n95`, `ffp2`), and `no (need for (a )?mask|mask (is )?needed)`, unless negated by `not`, `no`, `never`, `isn't`, `is not`, `aren't`, `don't`, `do not`, `cannot`, `can't`, `avoid`, or `unsafe` within the 4 words before the match.
5. Number and time grounding: every numeric value (`(?<![\d.])\d+(?:\.\d+)?(?!\d)`) in text fields must lie within ±1 of a number in `context` (`GUARD_NUMBER`), skipping pollutant names (`PM2.5`, `PM10`, `NO2`, `SO2`, `O3`, `CO`, `CO2`) and mask labels (`N95`, `FFP2`); GRAP stage references are exempt only when matching `context.grap_stage` (`GUARD_NUMBER` otherwise). Number words `hundred` and `thousand` are rejected anywhere; number words `one`–`ninety` are rejected when within 3 words of an air-quality metric (`aqi`, `pm`, `pm2.5`, `pm10`, `level`, `reading`, `index`, `ug`, `µg`, `micrograms`) and ungrounded. Clock expressions (including `am`/`pm`/`a.m.`/`p.m.`, `17:00`, `17.00`, and ranges like `4 to 6 pm`) are normalised to 24 h `HH:MM` and checked against `local_time`, `observed_time_ist`, `forecast` times (±30 min), or times in the user message (`GUARD_TIME`). Age durations are checked against `age_minutes`/`age_hours`; general-advice durations are skipped.
6. Length caps enforced by schemas (`extra="forbid"`). Any failure discards the reply; fallback once, then template.
7. Server grounding note (SAF-02): `/chat` adds `grounding_note` (`"This is a modelled estimate."` and/or `"Data is N hours old."`) when `source_label` is `Modelled` or `stale` is `true` and the AI answer omits those disclosures. Gemini/Groq `ChatReply` recommendations are forced to `tag="ai_wording"`.

## Symptom keywords (SAF-04)
Server enforces `needs_doctor_note=true` and `out_of_scope=false` (symptoms are in scope, also on templates; never cleared by AI) on normalised stems: `cough\w*`, `wheez\w*`, `breathless\w*`, `short\W*of\W*breath`, `asthma\w*`, `chest\s+(pain|tight\w*|hurt\w*|heav\w*)`, `breathing\s+(problem|difficult\w*|trouble|issue)`, `can'?t\s+breathe`, `cannot\s+breathe`, `khansi`, `khaansi`, `saans`, `dam\s+ghut\w*`, `phlegm`.

## Prompt injection
User text is delimited as untrusted; embedded instructions are ignored. JSON-only output, no tools, immutable verdict, 500-char cap, control characters stripped.

## Failure and fallback
Gemini (15 s), Groq once, then a rule-catalogue template with `generated_by:"template"` and the note "AI unavailable, showing standard advice".

## Privacy and transparency
Derived context only. Gemini's unpaid tier allows human review, so no names, addresses, exact coordinates or past chat are sent (A-03). Prompts are never logged. Every answer shows source chips and a Rule or AI wording tag.
