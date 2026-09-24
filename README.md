# The Half-Naked Halfling Benchmark

A local D&D Dungeon Master stress-test harness for long-duration agent performance: continuity, world state, rules consistency, NPC knowledge, causal consequences, interruptions, and correction recovery.

## Run locally

Python 3.10+ is required. The runtime uses the Python standard library.

```sh
cd outputs/half-naked-halfling
python3 local_app.py
```

Open the player URL printed by the server. The separate operator screen controls review and publication. Dice are generated locally and recorded, with durable protection against duplicate rolls.

- [Project guide](outputs/half-naked-halfling/README.md)
- [Local interface and rehearsal instructions](outputs/half-naked-halfling/LOCAL-PLAY.md)
- [Evaluation protocol](outputs/half-naked-halfling/PROTOCOL.md)
- [Verification record](outputs/half-naked-halfling/verification.json)

## Verification

```sh
python3 -m unittest discover -s outputs/half-naked-halfling/tests -v
python3 outputs/half-naked-halfling/audit_export.py outputs/half-naked-halfling/demo-run
```

The included 100-session demonstration is synthetic instrumentation testing, not evidence of live model performance. Unscored rehearsals are explicitly separated from independently reviewed benchmark runs. This is not a complete D&D rules engine.

## Public distribution

This repository includes source code, tests, the sample character and scenario, SRD reference material, and synthetic demonstration exports. Scenario/evaluator documents contain spoilers. Private campaign databases, session logs, operator credentials, API keys, and scratch work are excluded.

Live API calls are disabled by default. To opt in, supply your own `OPENAI_API_KEY` through the environment or an untracked `.env.local` in the repository root, then configure the model and limits. No credentials are included.

## SRD attribution

This work includes material from the System Reference Document 5.2.1 (“SRD 5.2.1”) by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.

See [attribution and transformations](outputs/half-naked-halfling/rules/ATTRIBUTION.md). The SRD license applies to that material; this publication does not assign a new license to the original project code.
