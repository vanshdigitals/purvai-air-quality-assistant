# Accessibility (owner of a11y requirements)

Target WCAG 2.2 AA.

| ID | Requirement |
|---|---|
| A11Y-01 | Text 4.5:1, large text and UI parts 3:1, both themes ([values](design/PURVAI_DESIGN_SYSTEM.md)) |
| A11Y-02 | Severity never by colour alone: word plus number plus icon |
| A11Y-03 | Full keyboard use, logical order, skip link, no traps |
| A11Y-04 | 2 px focus ring at 2 px offset on `:focus-visible` |
| A11Y-05 | Landmarks, one `h1` per page |
| A11Y-06 | Native controls first; segmented control uses radio group pattern |
| A11Y-07 | Visible labels; errors via `aria-describedby`; error summary focused |
| A11Y-08 | Verdict and AI replies `aria-live="polite"`; errors `assertive` |
| A11Y-09 | Charts have a text summary and table toggle |
| A11Y-10 | Accessible name "312, Very Poor, CPCB scale, Measured" |
| A11Y-11 | Reduced motion: 0 ms, no scale |
| A11Y-12 | 200% text resize; reflow at 320 px |
| A11Y-13 | Targets 44 x 44 px (above the 24 px minimum) |
| A11Y-14 | Modals trap focus, Esc closes, focus returns |
| A11Y-15 | `lang="en-IN"` |

Testing: axe-core in Playwright on every screen and theme (zero serious or critical), keyboard walkthrough, NVDA + Chrome and TalkBack before release ([TESTING.md](TESTING.md)).
