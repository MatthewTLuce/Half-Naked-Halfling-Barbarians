# The Half-Naked Halfling Benchmark

An operational prototype for long-duration Dungeon Master evaluation. Python 3.10+; standard library for runtime and search; rebuilding the PDF extraction additionally requires pypdf. Includes a live OpenAI Responses adapter, persistent campaign state, a human acceptance workflow, deterministic structural evaluation, an independent export reader, prompts, a provisional campaign seed, regression tests, and a synthetic endurance run.

**Status:** local prototype. Not a fully automated D&D rules engine, autonomous player simulation, or completed model benchmark. The API adapter is tested with mocked responses; no paid model campaign has been run. The new project key is stored outside this deliverable in the approved workspace `.env.local` and excluded from source control. Do not copy it into an export.

## Local Reza interface

The human pilot now has a local play screen and recorded click-to-roll dice. Run `python3 local_app.py` or `START.command`; open the printed player address. See [LOCAL-PLAY.md](LOCAL-PLAY.md) for operator review, launch, dice, call limits, and restart instructions. Live calls begin disabled; no opening has been published.

## Start a campaign

Run these commands from this deliverable's directory. Each CLI invocation resumes the same SQLite database. Do not use demo-run as a real campaign.

```sh
python3 hnh.py --db campaign.sqlite init
python3 hnh.py --db campaign.sqlite session
python3 hnh.py --db campaign.sqlite input --actor player:one 'Ada asks Mira who can authorize passage through the mountains.'
python3 hnh.py --db campaign.sqlite context
```

Choose the model under test explicitly. `MODEL_ID` below is a shell variable set to an API model available in your project, not a literal model name. A live invocation makes one paid request, with a 55-second client timeout, bounded output and no automatic retries. Context is the full current facts plus the selected number of recent records; no server conversation memory is used. API access and billing availability have not been tested live.

```sh
python3 hnh.py --db campaign.sqlite live --model "$MODEL_ID" --confirm-live-cost --max-output-tokens 4000
```

Inspect the returned proposal in an export or database, then accept it with the returned numeric proposal ID. Human acceptance authorizes fiction; it is not a quality score. The DM never receives a commit tool. For recorded/offline use, write the protocol JSON described in `prompts/dm.md` and call `submit proposal.json`.

```sh
python3 hnh.py --db campaign.sqlite export review-current
python3 hnh.py --db campaign.sqlite accept 5 --reviewer human-alice
python3 hnh.py --db campaign.sqlite reject 5 --reviewer human-alice --reason 'The seal was never transferred.'
```

The IDs above are illustrative; choose **one** resolution and use your actual proposal ID. Rejected proposals remain available to scoring. A failed structural check prevents acceptance and records a rejection. Semantically invalid proposals can pass structural checks; the independent reviewer must inspect them before accepting.

## Play and interruption

Give players only `prompts/players.md` and their permitted views. Keep evaluator material private. A local trusted operator runs the CLI; it is not an authenticated multi-user server. Do not give player or DM agents filesystem/shell access to the campaign directory.

```sh
python3 hnh.py --db campaign.sqlite context --actor player:one
python3 hnh.py --db campaign.sqlite context --actor character:pc_ada
python3 hnh.py --db campaign.sqlite context --actor orm
python3 hnh.py --db campaign.sqlite interrupt 'Stop: Bram never agreed to follow Ada. Keep him at the ferry.'
```

Run `interrupt` from another terminal while a request is pending, or between turns. It increments the interruption epoch immediately; a response generated from the older epoch cannot commit. The HTTP call is not canceled and can still incur cost. Generate a fresh proposal after the interruption. An out-of-character correction is recorded as an intervention, then resolved through a correction event naming superseded evidence. Never edit the database to repair campaign fiction.

Narration is an **operator-only draft**, not automatically sent to players. The operator routes passages to the intended audience; the prototype does not automatically redact semantic secrets in prose. Facts use explicit audience lists. Knowledge facts are private to their named actor plus DM. A player may know something its character does not; those are separate actors. Faction knowledge must be recorded separately from member knowledge.

## Inspect and evaluate

```sh
python3 hnh.py --db campaign.sqlite report
python3 hnh.py --db campaign.sqlite export run-export
python3 audit_export.py run-export
python3 hnh.py --db campaign.sqlite review --category 4 --verdict fail --evidence 7 12 --reviewer human-bob --opportunity npc-secret-001 --severity major --note 'Orm used Mira’s debt without a communication event.'
```

Use real evidence IDs. Reports distinguish automatic opportunities from independent human judgments and use null for untested rates. `PROTOCOL.md` defines the ten categories, denominators, evaluation windows and experimental controls. Raw requests, responses, errors, model names, token usage and latency stay in the ledger. No API authorization header is logged. Evaluator exports contain secrets and are never player packets.

## Verify locally

```sh
python3 -m unittest discover -s tests -v
python3 demo.py new-demo-run --sessions 100
python3 audit_export.py new-demo-run
```

Use a fresh demo directory; the tool refuses to reinitialize an existing campaign. `demo-run/` contains the supplied synthetic result. Its intentional errors demonstrate capture and rejection, not model failure. Its clock-only turns do not represent coherent gameplay, and unresolved winter consequences deliberately still require semantic evaluation.

## What is implemented and what remains operator work

Implemented: transactional event ledger and hash chain; explicit facts; actor projections; compare-before-write preconditions; correction and causal reference requirements; ruling-change protection; stale revision/epoch checks; raw API trace capture; recorded/live turns; process restart; ten-category reports; human judgments; independent export verification; 100-session synthetic run.

Operator responsibilities: complete character sheets and select relevant pages from the ingested SRD 5.2.1 corpus before testing mechanics; supply and log actual dice; route private narration; judge semantic changes, knowledge acquisition and causal plausibility; recruit experienced players; manage budgets and run sessions; independently score omitted facts and prose. No autonomous faction scheduler, model-driven player runner, streaming cancellation, full rule resolver or automatic semantic evaluator is claimed.

The data design and protocol support those extensions without changing the canonical log format. Keep this as the instrumented, human-adjudicated baseline when comparing more autonomous versions.

## Sources

The API request follows [official OpenAI text-generation documentation](https://developers.openai.com/api/docs/guides/text). The demonstration pins [D&D SRD 5.2.1](https://www.dndbeyond.com/srd), now bundled from the user-supplied PDF as a pinned reference corpus; this does not implement the full rules mechanically. The setting, prompts and benchmark procedures here are original. Source pages were checked during implementation on September 4, 2026.


## Ingested SRD 5.2.1

All 364 PDF pages are preserved and indexed in `rules/`. See [the ingestion report](rules/INGESTION.md). The original PDF is copied unchanged, with attribution and SHA-256 provenance. New campaigns pin this source hash in genesis. Earlier logs and the supplied synthetic run retain their original manifests; the first selected packet records the source for an earlier campaign. No existing campaign facts were changed during ingestion.

Search, inspect, then select complete pages into a campaign:

```sh
python3 rules.py search 'Fireball'
python3 rules.py search 'Unarmored Defense'
python3 rules.py pages 28 29 30
python3 hnh.py --db campaign.sqlite rules --pages 28 29 30 --reviewer human-alice
```

`rules` records the exact selected text, page IDs and source hashes in the campaign ledger, replaces the active packet, and increments the interruption epoch. The DM's next context and logged API request include that packet; the independent evaluator can inspect the same evidence. Prior packets stay in the ledger. Select adjacent pages and glossary definitions as needed; up to twelve complete pages fit a single packet. There is no automatic search inside the live model loop yet.

The source is reference data, not agent instructions. Search ranks headings and lexical matches; it cannot guarantee semantic completeness. Raw extraction preserves PDF line breaks and hyphenation; normalization is only for search. Verify ambiguous tables and symbols in the PDF. No paid API call was used for ingestion.
