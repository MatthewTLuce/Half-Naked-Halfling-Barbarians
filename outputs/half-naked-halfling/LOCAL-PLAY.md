# Reza's local table

## Current pilot: unscored rehearsal

The user selected an unscored, chat-operated rehearsal on September 8, 2026. Reply in the Codex conversation; the assistant reads any actions entered in the local table when continuing that conversation and synchronizes approved rehearsal narration and dice. The browser action box does not automatically wake the assistant. Use the browser for requested rolls. No paid API calls are enabled. Rehearsal commits explicitly record no independent reviewer, and the report marks them ineligible for benchmark quality scoring. Independent semantic evaluation remains deferred. The live human-review baseline described below remains available as a separate condition.


Run `python3 local_app.py` from this folder, or double-click `START.command`. Requires Python 3.10+; no installation of web packages is needed. Open http://127.0.0.1:8876/play. Keep the launcher terminal running; Ctrl+C stops it. Restarting resumes the same campaign. If the port is occupied, use `python3 local_app.py --port 8877` and the printed address.

## For the player

The screen shows Reza's accepted equipment, spells, HP, slots, reactions, conditions, approved narration, and dice. Type actions freely. Use **Pause / clarify** with your correction written in the action box to invalidate pending decisions. It does not erase accepted history or completed rolls.

When **Roll dice** appears, its purpose and modifier have already been approved. Click once. The server generates the dice using operating-system randomness and records the raw dice, modifier, total, request and source before returning the result. Repeated clicks, network retries, refreshes and restarts reuse that result. Advantage and disadvantage record both d20s. There is no model-selected die result or silent reroll.

A changed situation pauses outstanding rolls for operator review. Correcting a bonus preserves the original dice and total. Damage, healing, spell slots, concentration and reactions update only through an accepted state change; rolling does not itself apply an outcome. Displayed AC is base AC; temporary effects belong in recorded conditions and the reviewed ruling.

## For the independent operator — contains workflow details, not campaign answers

Open `/operator` on the same server. The launcher prints the location of `local-data/operator-key.txt`; enter its contents in the operator login. Keep this view and audit exports away from the player. Login is a local convenience boundary; this is not an adversarial multi-user hosting service. The server binds only to loopback and does not expose files by directory browsing.

1. Enter your reviewer name. Start session 1 when ready. The Reza pilot is separate from the old demonstration campaign, with a fresh ledger and no published opening.
2. Complete private setup, including Ambrosia's still-unpinned ghost mechanics, and load relevant complete pages from the supplied SRD. `python3 rules.py search 'Shield'` finds page references. Review ambiguous source tables in the original PDF. A rules packet is evidence, not automatic rules enforcement.
3. Either submit an offline protocol proposal, or explicitly select an available API model, enable calls and save the campaign call limit and per-call output limit. Then choose **Generate one DM proposal**. Existing workspace credentials are read by the adapter. This interface made no paid calls during development. Limits bound calls and output, not dollars; failed/interrupted requests count, and there are no automatic retries. Disabling calls prevents future launches; it does not cancel an in-flight request.
4. Inspect each proposal and its checks. Explicitly enter only player-safe narration in its publication box, then accept. A blank box publishes nothing. Structural checks do not establish that prose is free of secrets or that rulings are correct. Reject mistakes with reasons. The DM has no acceptance tool; an independent reviewer must make these decisions.
5. Approve requested rolls, let the player roll, then generate/review the resulting outcome. Private rolls appear only in the operator view. Source record IDs connect rolls and consequences to their causes. Resource edits capture their starting revision, so edits loaded before new activity must be reloaded and reviewed.
6. Use explicit correction events with evidence for accepted mistakes. A roll-modifier correction does not automatically repair damage or other downstream consequences; record those compensating state changes separately.
7. Record evaluations with evidence IDs across the ten categories. Start each session explicitly. Download private audit exports at session boundaries and preserve copies outside the working campaign directory.

If one person is both player and operator, campaign surprises may be spoiled and independence is weakened. For the intended blinded pilot, another person should operate/review; model judgments alone do not meet the benchmark's independent evaluation requirement. Reviewer names are recorded attribution, not proof of independence.

## State, export and validation

`local-data/campaign.sqlite` contains the permanent campaign ledger and request retry receipts. The operator key and campaign data are excluded from the distributable ZIP. Do not remove this directory to update the application. For a separate pilot use `--data-dir /path/to/new-directory`; do not run multiple servers against the same data directory. Original character files remain provenance; runtime resource values are stored in the pilot ledger.

The operator export is a single JSON file. Check it without importing the DM runtime:

```sh
python3 audit_export.py /path/to/hnh-private-audit.json
```

The independent reader verifies the record chain, replays committed state, checks the snapshot, and recomputes recorded dice arithmetic. Retain an external copy of each head hash/export: a hash chain alone cannot prove authenticity against someone rewriting both the entire log and its anchor. Randomness quality and semantic correctness require evidence beyond arithmetic checks.

Verification: 56 automated tests passed, including HTTP access boundaries, duplicate concurrent clicks, restart persistence, corrections, stale proposals, mocked call budgets and independent audit tampering checks. JavaScript syntax checks passed. The older 100-session synthetic export still verifies. Browser appearance and interaction have not been visually tested; no live model campaign or long-duration model-performance claim has been made.
