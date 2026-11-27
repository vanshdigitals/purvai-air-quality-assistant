# AI Behaviour and Safety (owner of AI rules)

**SAF-01:** the deterministic rules engine decides the safety verdict. AI only explains and personalises. AI cannot downgrade or override a warning, compute AQI, diagnose or invent data.

System instructions: plain words; use supplied context only; cite fields; say "I don't have that data" when missing; never contradict `verdict.level`.

SAF-02 grounding: each call has AQI, category, source label, time and verdict. Modelled data must be called "modelled estimate". Stale data must state its age.
SAF-03 no diagnosis, medicine, dosage, cures, or claims that masks or purifiers make air "safe".
SAF-04 respiratory or chest symptoms set `needs_doctor_note=true`; UI adds "Consult a doctor".
SAF-05 sensitive groups get stricter wording. Masks: well-fitted N95/FFP2; BIS IS 9473 marking unverified, so no standard number is claimed.

## Guard and contradictions
Server checks: verdict equality, action IDs in the allowed list, banned phrases, and every number in the answer must appear in context (within plus or minus 1). Any failure discards the reply; fallback once, then template.

## Prompt injection
User text is delimited as untrusted; embedded instructions are ignored. JSON-only output, no tools, immutable verdict, 500-char cap, control characters stripped.

## Failure and fallback
Gemini (15 s), Groq once, then a rule-catalogue template with `generated_by:"template"` and the note "AI unavailable, showing standard advice".

## Privacy and transparency
Derived context only. Gemini's unpaid tier allows human review, so no names, addresses, exact coordinates or past chat are sent (A-03). Prompts are never logged. Every answer shows source chips and a Rule or AI wording tag.
