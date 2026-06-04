# BRUIN_SHARED_MEMORY

Persistent context for the Bruin Command Center (Drayage CC) Airtable
automation work. Append new dated entries when something is settled that
future sessions shouldn't re-derive. Keep entries short.

---

## Project handles

- Airtable base: `appFOrEfSmre47N1a`
- Command Center table: `tbl9jFQAOqHj7bvof`
- State-machine fields:

  | Name | ID | Type |
  |---|---|---|
  | Status Snapshot/Previous | `fldrDUPPcofstcCQo` | singleLineText |
  | Status Change Timestamp | `fld1CO6bZuzurSdBV` | dateTime (UTC) |
  | Invalid State Flag | `fldoR5M0inn764UvB` | checkbox |
  | Invalid State Reason | `fld42dD3AxVnzqOlG` | multilineText |
  | Last RED Alert Sent | `fldqyS4igm9L2HRjO` | date (day granularity) |

## Operational notes (apply to all future sessions)

- Airtable API/MCP does NOT expose automation script source. To audit
  scripts, a human must open the automation -> Run a script -> Edit
  code -> select-all + copy -> paste. Programmatic browser-MCP
  extraction has been unreliable (multiple hard crashes 2026-06-04).
- Pasted bodies may contain webhook URLs / tokens — sanitize before
  sharing in any public channel. Secret-scanning filter has blocked
  some reads.
- Condition rows and action types ARE visible on the flow panel
  without copy-paste; use that for guard/dedup audits before asking
  for full script bodies.

---

## 2026-06-04 — Automation reconciliation pass

### Resolved (do not re-litigate)

- "CC State Machine — Consolidated" replaces old Automations
  #1 / #2 / #3 (per its own header).
- "Install Script 01 copy" + "Install Script 02" are the leftover
  #1 / #2 and are queued for deletion per the cutover plan.

### Loop diagnosis — verdict: re-entrant write loop CONFIRMED (structural)

Offending automation — **Install Script 02 "Revert Invalid State"**
(phase 2, ON, ~52 runs/mo):

> TRIGGER: "When a record matches conditions: If State Valid? contains
> 'INVALID_CROSS_LE...'" — single condition, **NO
> `Last Modified By is not [Automations]` guard.**

Mechanism: unguarded trigger fires on `State Valid?` containing
`INVALID_*` -> script batch-reverts Status/Snapshot across affected
records -> automation-authored Status writes satisfy every other
update-driven "matches conditions" automation (no guards) -> cascade
re-fires (~7×/record observed).

Empirical evidence from live table at session time:
- `Invalid State Flag`: 0 records currently set.
- 11 records had `Status Change Timestamp` updated in past week; 10 of
  them share the EXACT timestamp `2026-05-21T05:46:41.708Z` —
  signature of a single batch script writing across 10 records in one
  pass.
- `Last RED Alert Sent`: only 2 records ever stamped, both 2026-05-21.
- ~70 dispatch Telegram messages / ~10 active records ≈ 7×/record →
  rules out "many distinct records"; consistent only with re-firing.

Caveats (carry these forward):
- The 05:46:41.708Z batch is *consistent with* Install 02 but not
  *uniquely* proven to be it; the consolidated SM's snapshot writer
  could produce the same signature.
- "Approaching LFD — three-tier escalation" is **email-only**
  (3× Send-email tiers; no webhook, no script). It contributes to the
  email cascade — no guard, re-fires on Status churn — but does NOT
  send Telegram and does NOT stamp `Last RED Alert Sent`.
- The actual **Telegram sender was not viewed this session**.
  Suspected: a separate webhook / Make automation that also writes
  `Last RED Alert Sent`. Identifying it only matters for adding dedup
  at the sender; the root fix (Install 02) should stop the cascade
  regardless.
- "Approaching LFD" carries an UNPUBLISHED EDITS banner — published
  version may differ from the editor read.

### Auto-4 (Phase 5, ON, ~25 runs/mo) — KEEP (provisional)

- Trigger: `Total Legs = 0 AND Shipper is not empty ...` — self-
  limiting (stops matching once legs exist), so not a re-entrant loop
  driver even without a `Last Modified By` guard.
- Action: Run a script (leg-init sibling of Auto-1 / Auto-2).
- **Open:** "every field it writes" requires the script body, which
  was not captured this session (browser MCP crashes). Grab from the
  Airtable UI when convenient. KEEP classification stands either way.

### Worklist for Taranjot (read-only analysis output)

1. **Delete or guard Install Script 02 — root fix.** Add
   `Last Modified By is not [Automations]` to its trigger, or delete
   per cutover (it is superseded by CC State Machine — Consolidated).
2. Add the same guard to "Approaching LFD — three-tier escalation";
   resolve its unpublished-edits banner.
3. Locate the Telegram sender (the automation that stamps
   `Last RED Alert Sent`) and add dedup there if belt-and-suspenders
   desired.
4. Capture Auto-4 script body to finalize its field-write inventory.
