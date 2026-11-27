# Purvai Design System v1.1 (single source of visual truth)

## Brand
Purvai means "the eastern breeze". Positioning: "For families in polluted Indian cities, Purvai is the air safety companion that turns official air data into a clear daily plan. Unlike AQI dashboards, it tells you what to do now and shows what each choice changes." Tagline: Know the air. Act in time. Personality: calm, clear, trustworthy, practical. Logo: "Open P" (blue canopy, teal breeze, open gap), not trademark-cleared (A-06). Principles: action before information, calmness under pressure, evidence before explanation, consistency, accessibility, minimalism.

## Colour
Primary Harbor Blue #1E4E79, accent Clear Teal #0E7C86, supporting Graphite #334155.

| Token | Light | Dark |
|---|---|---|
| bg | Mist #F7F8FA | Night #0B1220 |
| surface | #FFFFFF | Deep Slate #121A2B |
| subtle / raised | Cloud #EEF1F5 | Slate 2 #1A2438 |
| text / text-2 / muted | Ink #0F172A / Slate #475569 / #5B6578 | Frost #E6EAF2 / Steel #A3ADC2 / #8B96AD |
| border / input | Haze #E3E6EB / Slate Line #7B8598 | Line #2A3550 / Line Strong #5B6785 |
| primary | #1E4E79, hover #1C486F, pressed #1A4368 | Harbor Light #7FB2E5 (Night text), #8EBBE8, #9BC3EB |
| accent | #0E7C86 | Teal Light #4FC3CE |
| secondary tonal | #E8EDF2 / #DBE3EA / #CED8E2 | tonal on raised |
| selected | #E8EDF2 | #212F45 |
| disabled bg / text | #EEF1F5 / #7B8598 | #1A2438 / #5B6785 |
| focus | #1E4E79 | #7FB2E5 |

Semantic (system states only, never AQI): danger #B42318/#F97066 (--on-danger #FFFFFF/#0B1220, #FEF3F2), warning #B54708/#FDB022 (#FFFAEB), success #067647/#47CD89 (#ECFDF3), info #175CD3/#7FB2E5 (#EFF8FF).

AQI (CPCB categories): Good #2E9E5B, Satisfactory #8BC34A, Moderate #E8C547, Poor #E8892B, Very Poor #D64545 (P-01: #CF4040 on filled chips, white text 4.71:1), Severe #8E2430. Use only as dots, 4 px bars, 8%/12% chart bands and chips, always with the word. P-02 hairline ring. Official CPCB colour codes unverified.

Contrast (computed): Ink on White 17.85; White on Harbor Blue 8.67; Slate Line on White 3.72 (borders only); Frost on Night 15.53; Night on Harbor Light 8.38; Caution Amber on White 5.43.

## Typography
Instrument Sans (headings, key UI; 500/600); Geist (body, labels, data; 400/500/600; `tabular-nums`). No Devanagari (P-03).

| Style | Size/line | Weight |
|---|---|---|
| display | 48/53, -0.02em | 600 |
| h1 / h2 / h3 | 32/38, 24/30, 20/26 | 600, 600, 500 |
| aqi-hero (Geist) | 72/72 tabular | 600 |
| body-lg / body / small | 18/29, 16/26, 14/21 | 400 |
| label / data | 14/20 | 500 (data tabular) |
| caption | 12/17 | 400 |

## Tokens
Spacing 4, 8, 12, 16, 24, 32, 48, 64. Radius 6 (inputs, chips, buttons), 10 (cards), 999 (pills). Shadow `0 1px 2px rgba(15,23,42,.06)` light only; dark uses tonal elevation. 1 px borders. One gradient, Mist to White behind the Air Now hero (light). Breakpoints 640/1024/1280. Grid 4/8/12, gutters 16/24. Widths 1120 dashboard, 720 reading. Sidebar 232, bottom nav 68, targets 44. Motion: 150 ms hover/press, 200 ms selection, `cubic-bezier(0.2,0,0,1)`, press scale 0.98 buttons, 0.99 cards; reduced motion 0 ms, no scale.

## Interaction rules
Hover changes background tone only, inside `@media (hover:hover) and (pointer:fine)`, never border, outline or ring. Pressed: one step deeper plus scale. Focus: 2 px ring, 2 px offset, `:focus-visible` (text inputs on any focus). Disabled: neutral disabled tokens for every variant. Selected: check mark, selected tint, 1.5 px inset border on cards. Error: danger border, icon, message.

## Components
- Buttons: Primary, Secondary (tonal), Tertiary (neutral fill), Ghost, Danger, Danger subtle, Icon-only, Loading, Disabled; heights 36/44/52; padding 16 (14 with leading icon); icons 18 px.
- Selection: segmented (2 to 4 instant options), option cards (report format), checkbox cards (household), list rows with trailing check (locations), tiles (commute), toggles (instant settings), filter chips (activity), checkbox (single yes/no). Radio lists are not default.
- Inputs and selects 44 px, radius 6, Slate Line border, label above, helper or error below. Cards radius 10, 1 px border, 16 to 24 padding. Chips carry the category word.
- Alerts: semantic tint plus icon plus text; GRAP banner is info style with stage and order date.
- Navigation: bottom nav under 1024, sidebar 232 above; active item uses selected tint and label. Modals max 480, focus trap. Tooltips never hold essential information.
- Charts: Recharts, AQI bands 8% (12% dark), tabular axes, table toggle.
- AQI hero: aqi-hero number, category word, scale label, source chip, 4 px bar. Verdict card: headline, member note, Rule tag. Chat: user bubble on subtle, assistant on surface, data chips, AI wording tag.
- Loading skeletons on Cloud/Slate 2; empty: icon, one line, one action; error: danger subtle with retry.

## Screens and responsive
Onboarding (720 single column), Today (hero, verdict, 3 actions, forecast), Daily Plan (4 period cards), Ask Purvai (thread and composer), Home Air (calculator, tips), Impact (totals, log), Reports (option cards), Settings (grouped rows). Mobile under 640: 4 columns, bottom nav. Tablet 640 to 1023: 8 columns. Desktop 1024+: 12 columns, sidebar, max 1120.
