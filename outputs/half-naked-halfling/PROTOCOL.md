# Experiment specification — version 0.1

## Purpose and unit of evaluation

Test whether a DM maintains a coherent, open world across many sessions despite ordinary creative play and deliberate pressure. A fluent encounter is insufficient. The primary observational unit is an independently identified opportunity: a recalled fact, a state transition, a rule application, a knowledge use, a faction action, a delayed consequence, or a recovery step. A session and a campaign are clustering units, not interchangeable independent samples.

This prototype uses an instrumented DM: full explicit state plus bounded recent history, with a human canonical-state steward. Scores describe performance with that scaffolding, never unaided model memory. The steward must not silently rescue mistakes. Preserve the original proposal, failed checks, rejected fiction, explicit intervention, repaired proposal and subsequent consequences. Report both attempted failures and committed failures.

## Canonical data and audit contract

The append-only application log is SQLite `records(seq, kind, payload, prev, hash)`. A transaction serializes writes. SHA-256 links canonical JSON records; exports include the final digest. Copy that digest to evaluator-controlled storage at each checkpoint. A hash chain detects edits against a trusted prior anchor; a local operator able to rewrite the entire database and anchor can forge it. There is no cryptographic signature or adversarial filesystem security claim.

Genesis pins scenario and rules manifest and explicit facts. Each fact is `{value, audience}` keyed by a stable ID such as `entity.pc_ada.location`, `item.ferry_seal.owner`, `ruling.authority`, or `knowledge.orm.pass`. State is replayed from genesis and accepted commits. Snapshots are derived artifacts; the separate audit reader checks them against the ledger without importing DM runtime code.

Each event contains a kind, explanation, causal record IDs, superseded record IDs and exact before/after changes. Kinds cover actions, rulings, state changes, promises, discoveries, deaths, possessions, faction changes, geographic changes, consequences, corrections, knowledge and improvisation. Entity creation is prospective; IDs are never reused for another person. An ownership field represents one owner at a time; transfers change that field rather than copying the item. Quantities, containers and destroyed objects require explicit additional facts. Do not silently resurrect an entity or duplicate an object under a new ID.

Use nested value objects for promises (speaker, recipient, terms, status, due date), obligations (cause, review time, status, resolution evidence), routes (endpoints, travel time, access), faction plans (decision makers, goals, resources, commitments), and messages (sender, recipient, content, departure and arrival times). These semantic shapes are conventions; only the core event envelope and listed invariants are enforced automatically in v0.1. The evaluator must catch omissions and unsupported additions.

Knowledge separates canonical truth from a claim someone believes, with a source describing observation, message or testimony. A false belief is allowed. `audience` is access to a record, not proof that an NPC witnessed an event. No one acquires knowledge just because the DM or another actor has it. Model-proposed visibility changes also require human scrutiny.

Corrections append compensating facts and identify superseded evidence. Earlier events remain historically visible. Review downstream possessions, promises, beliefs and causal chains individually; never assume changing the root fact repaired them all. A correction of the record differs from an in-world event such as resurrection or a changed political decision.

## Independent scoring rubric

For each category, record eligible opportunities, pass, fail, uncertain and untested; severity; evidence IDs; fact age in turns/sessions; and evaluator identity. Automatic rate is passed checks / evaluated checks. Human rate is passes / (passes + failures); report uncertain counts separately. Proxy checks are not substitutes for semantic correctness. Do not combine automatic and human denominators.

| Category | Automatically checkable in this implementation | Independent human judgment and measurable outcome |
|---|---|---|
| 1. Continuity accuracy | Explicit pre-turn assertions match current canonical facts; rejected false assertions count | Identify every recalled claim in prose, including claims omitted from assertions. Correct recalled claims / decidable recall opportunities; record invented history and age of supporting evidence. |
| 2. World-state accuracy | Exact preconditions, unique writes within a proposal, valid fact envelopes, nonnegative selected resources, existing locations and owners, snapshot replay | Compare each material outcome to prior state and action. Correct complete transitions / transition opportunities; count omitted costs, duplicated entities, wrong time/location and unlogged changes. |
| 3. Rules fidelity and ruling consistency | Established ruling keys cannot change without an explicit correction | Separately score rule applications against pinned SRD text and equivalent-case consistency against ruling history. Include rule reference, relevant stats, resource spend and dice. Missing rule packet is untested, never correct. |
| 4. NPC knowledge boundaries | Explicit knowledge assertions exist and match; knowledge-record audiences confined to the named actor and DM | Legal uses of knowledge / NPC knowledge-use opportunities. Inspect speech and strategy for leaked secrets; verify observation/communication and false-belief persistence. |
| 5. Multi-agent/faction consistency | No direct semantic scoring; state invariants are category 2 proxies only | Coherent independent decisions / faction decisions. Check authority, motives, resources, asymmetric beliefs, conflicting goals, message delays and agreements. Shared objectives are not shared minds. |
| 6. Long-range causal consistency | Cause IDs exist; time does not silently reverse | Supported and addressed delayed consequences / matured consequence opportunities. Inspect causal relevance, dependency chains, dropped obligations and effects after 1, 5, 10 and 25+ sessions. Existing citation alone earns no causal credit. |
| 7. Recovery from interruption or correction | Stale epochs rejected; corrections must reference existing superseded evidence | Record turns to recover, downstream repair completeness, continued compliance over next three relevant opportunities, and recurrence rate. An apology is not recovery. Measure interrupted accepted side effects separately. |
| 8. Improvisational coherence | No automatic semantic score | Plausible, non-retroactive, rules-compatible responses / novel action opportunities. Reject forced solutions and arbitrary vetoes; accept multiple coherent outcomes. Judges explain the alternative possibilities rather than demand one answer. |
| 9. Resistance to player-induced contradictions | No direct semantic score; false explicit claims may be detected in categories 1/4 | Contradictory inputs handled without corrupting canon / contradiction opportunities. Distinguish malicious claims, sincere mistaken recall, ambiguous evidence and valid corrections. Blind refusal of a true correction is a failure too. |
| 10. Overall campaign coherence | No automatic semantic score | Independently rate each reviewed session window 1–5 on persistent identity, causal intelligibility, fair consequences and usable player agency; also record pass/fail/uncertain with justification. A major unresolved inconsistency caps the window at 2; strong prose cannot offset corrupted state. Store the numerical rating in review note. |

Suggested severity: minor = local discrepancy with no meaningful downstream effect; major = changes a decision, rule outcome, resource, relationship or secret; critical = corrupts a major campaign trajectory or persistently erases accepted player agency. Retain multiple category labels in evaluator notes, but use one primary category per opportunity when aggregating failures to avoid double counting. The CLI prevents duplicate reviewer/opportunity entries; disagreements from different judges remain separate.

## Long-duration study design

Start with at least 50 sessions per campaign and plan 100; use multiple independently seeded campaigns and player groups, not one endlessly repeated encounter. A practical pilot is 6 campaigns of 50 sessions, expanding only after evaluator calibration. Record actual turns, elapsed fictional time and wall time because session lengths vary. These are proposed design sizes, not a power calculation.

Freeze the rules edition, relevant rule packets, character sheets, model ID/snapshot, prompt content/hash, scenario hash, context policy, budget, and operator procedure before collecting comparisons. Log later provider changes or prompt revisions; treat them as a new experimental condition. Requests preserve prompts and model ID, responses preserve returned provider metadata, tokens and latency. A seed alone does not make stochastic model calls reproducible; retained responses enable exact recorded analysis.

Review early (sessions 1–10), middle (21–30), late (41–50) and each later ten-session window. Match opportunity types and fact ages when estimating degradation. Report error rates and uncertainty by category, age bucket and campaign; bootstrap confidence intervals by campaign, not by individual assertions. Fit session-index trends only after controlling for changing difficulty and fact age. No trend is produced from the synthetic demo because it contains injected errors on a schedule.

Primary longitudinal measures: failure rate per eligible opportunity; major/critical failures per 100 opportunities; time to first major continuity break; recovery turns and recurrence within the next three relevant opportunities; unresolved obligations per matured obligation; independent overall-coherence ratings. Also report completion/abandonment, API failures, token use, latency and human interventions per session. Campaigns that collapse remain in the dataset; do not analyze only survivors.

Prefer human experienced players for the baseline. For later AI-player conditions, give each player agent only its player/character packet, private objectives and player prompt. Run faction agents with separate private state, communication records and budgets. Do not give them the evaluator key or let the tested DM generate all adversarial actions. This version supports actor projections and logged inputs but does not launch those separate agents automatically.

Use two blinded external evaluators for semantic categories. They independently identify opportunities, then reconcile disagreements while retaining initial labels. A different model may propose annotations but cannot be the sole judge. Calibration uses development recordings; reserve campaign seeds, groups and novel actions for holdout. Score omission frequency independently to detect a DM gaming the benchmark by making fewer explicit assertions.

## Pressure without a scripted solution

Offer experienced players competing interests and scarce resources, not a checklist of clever moves. Their choices determine which pressures emerge. Separately label natural play and operator-injected perturbations; report them as different strata. The operator may introduce a scheduling interruption, an ambiguous witness report or a disputed recollection at varying times, but cannot choose the correct solution or secretly change established facts.

Examples of pressure dimensions, not mandatory scenes: party separation with travel time; an NPC hearing a false rumor; an item returning after many sessions; competing factions negotiating through imperfect messengers; reopening an old ruling; a valid correction mixed with an invalid demand; off-screen consequences maturing while the players pursue another goal; a plan using terrain or institutions in an unanticipated way. Randomize timing independently of success and retain the injected input verbatim.

## Initial demonstration: a border under pressure

Read `scenario.json` as provisional original world state. Reedbank's ferry connects trade to a high pass and the Giant homeland. Independent halfling clans need winter grazing; giants want secure settlements; the ferry guild wants commerce. Mira, Tavi and Orm have distinct interests and partial knowledge. An allegation of a giant raid is unresolved. A cargo seal has no border authority. The pass is snowbound. None of those facts forces a quest or war.

A Horde of Half-Naked Halfling Barbarians is a possible player-created political and military development, not a timer or a hidden required scene. Clothing is descriptive. The DM must establish recruitment, individual clan decisions, command or coordination, reason to invade, movement and supply, and what the defenders can learn and do. These are causal questions, not a fixed numerical unlock condition. Players may invent other plausible means, including unexpected transport or alliances, whose mechanics and costs must be adjudicated.

There is intentionally no `invasion_ready` predicate, progress bar, fixed troop threshold, compulsory villain or success bonus for war. Trade, an autonomous clan raid, famine mitigation, migration, a giant invitation, failed mobilization and no contact are also possible. The benchmark evaluates the coherence of what actually happens. It does not grade whether the title event appears.

## Implementation limits and extension contract

The current live loop produces one JSON proposal per request and pauses for an independent human steward. This bounds corruption while retaining the attempted error signal. It is not an autonomous end-to-end campaign runner. To measure uncontrolled degradation, build a separate labeled condition with an independently specified automated world arbiter; do not quietly remove human acceptance from this baseline.

Current campaign state is supplied in full, with an operator-selected SRD page packet, so context size grows with campaign complexity. There is no automatic compaction/retrieval optimizer. Requests fail visibly if they exceed provider limits; this is an infrastructure outcome, not a continuity pass. A future retrieval condition must log every query and returned fact, preserve an evaluator-complete state and measure missed retrieval separately from ignored evidence. Long-term forgotten obligations and inaccessible historic records require explicit evaluation, even if the current-state packet remains short.

The runtime verifies IDs and structural constraints, not the semantic relevance of a cited cause, the truth of invented knowledge acquisition, all D&D mechanics, or complete prose-to-state extraction. Hash integrity is not truth. Human reviewer identities are labels within a trusted local operator boundary, not authentication. Persist checkpoints outside that boundary for auditable experiments.


## SRD ingestion addendum

The user-supplied SRD 5.2.1 has been ingested as 364 page records. Its source hash is `8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87`. `rules_packet` records preserve complete selected pages and hashes outside editable campaign facts. Rules-packet changes invalidate earlier proposal epochs. Selection is performed by the operator, not autonomously by the DM; log missing retrieval separately from ignored or misinterpreted evidence. The packet is reference data and conveys no authority to execute instructions in the document. Existing synthetic results predate this integration and remain unchanged.
