# Gauntlet: Design Doc

Nov 16, 2026 · Sai Praneth K

## Summary

Gauntlet is a research assistant for anyone with a question. It reads the sources, builds a sourced answer, and along the way proposes new ideas and tests the ones it can. Cheap models do most of the reading and testing. A stronger model checks the work. The person decides what to trust.

The one-line idea: every claim in the report shows how it was checked. A fact from a source carries its quote. A new idea carries the test it passed or failed, or says it is untested. Nothing is shown as more certain than its evidence.

Who it is for: students, researchers, analysts, journalists and curious people. Starting needs only a question. Experts can plug in their own sources and test tools.

What it is not:

- Not a novelty machine. New ideas are a by-product of research, each labelled untested, tested or refuted.
- Not an oracle. Where evidence is thin or sources disagree, the report says so.
- Not a substitute for the sources. Every claim links to the passage or test behind it.

## Background

Gauntlet generalises the loop used in PhysicsC191A (quantum linear-system readout). That run produced two results that survived checks and were not found by search. It also produced many wrong claims, all caught by review.

What worked:

- Cheap models at volume. They tried many angles, wrote test scripts, downloaded 32 papers and built three independent replications (8.51×, 8.21×, 7.99× fewer shots on a fluid-solver experiment).
- Adversarial pairing. A Prover and a Breaker attacked each question in parallel.
- Executable checks. Every claim had a script whose output outranked any agent's report.
- Strict wording rules. No agent could write "novel" or "proved" without the referee's verdict.

What failed, and was caught only by review:

| Failure | What happened | Check that would have caught it |
|---|---|---|
| Answer-fitted simulation | Circuit sim tuned to the known answer | Held-out instances, random seeds |
| Fake resource counts | Gate counts from random unitaries | Recount from the actual circuit |
| False lower bounds (×3) | Proof covered named strategies only | "For all strategies" audit |
| Scale mismatch | 11.3× speedup was really ~8× | Unit and scale match on compared numbers |
| Novelty overclaim | Result partly in arXiv:2610.08890 | Librarian must quote the closest paper |
| Refuted claim left as PROVED | Ω(κ/ε²) stayed in the question list | Notebook re-audit each cycle |

The lesson for a general tool: the value came from reading widely and checking every claim. The new ideas were a result of that research, not a separate hunt. Gauntlet puts research first and keeps the checks.

## Goals and non-goals

Goals:

1. Answer research questions in any field, starting from a plain-language prompt.
2. Explore new ideas during the research: propose them, test them where a test exists, and label them honestly.
3. Make every claim traceable to a quoted source or a test output.
4. Keep cost low by default: cheap models for volume, a strong model for judgement, cost shown before a run.
5. Write for the reader: a plain-language report on top, an expert appendix underneath.
6. Run on common agent runners (Claude Code, opencode and others) with no custom servers.

Non-goals:

- Deciding truth or novelty for the user.
- Writing papers for submission.
- Running lab experiments or collecting new data.
- Giving medical, legal or financial advice. It reports research on these topics and says it is not advice.

## Architecture

One research loop in six stages. Exploring new ideas is one stage inside it, fed by the gaps the reading turns up. Each stage is run by subagents with self-contained briefs.

The Check stage can send work back to Survey when a claim lacks a source. The person can ask a follow-up after any report, which starts a new round on the same notes.

| Stage | Role | Model tier | Output |
|---|---|---|---|
| Scope | Orchestrator restates the question, sets depth and budget, asks one clarifying question if needed | Strong | Research plan |
| Survey | Readers search, save each source, extract quoted passages | Cheap, parallel | Source notes |
| Synthesize | Synthesizer maps what sources agree on, disagree on, and leave open | Strong | Evidence map + gaps |
| Explore | Ideator proposes ideas from the gaps; Prover and Breaker test the checkable ones | Cheap | Idea log with test results |
| Check | Referee confirms quotes match sources and tests reproduce | Strong | Labelled claims |
| Report | Writer produces the answer at the reader's level | Mid | Report + expert appendix |

Depth modes let a general user control time and cost:

| Mode | Sources | Idea testing | Typical use |
|---|---|---|---|
| Quick | ~10 | None; ideas listed as untested | A first look at a topic |
| Standard | ~30 | One round on the top ideas | A class project or a work brief |
| Deep | 50+ | Repeated cycles until stop conditions hold | A research project |

Model routing is a setting, so users can pick which models fill each tier. Deep mode stops when cycles run out, budget is spent, or three cycles add no new evidence.

## Topic setup

A general user should not have to configure anything. In the Scope stage, the orchestrator writes a short topic profile from the question: the field, where to look, how ideas can be tested, and the reader's level. The user can accept it or edit it in plain words.

| Field | Where it looks | How new ideas get tested | If no test exists |
|---|---|---|---|
| Math, physics, theory CS | arXiv, textbooks | Numerics on many instances; proof checker if available | Labelled untested |
| Software, engineering | Docs, repos, standards | Benchmarks against a baseline | Labelled untested |
| Economics, policy | Reports, public datasets | Statistics on public data | Labelled untested |
| Medicine, biology | PubMed, systematic reviews | Re-analysis of published data only | Labelled untested; not advice |
| History, humanities | Primary sources, archives, scholarship | Checked against documents | Labelled as interpretation |

Experts can go further with an optional expert pack: seed papers, their own test scripts, a list of mistakes common in the field, and notation. The quantum-readout work from PhysicsC191A becomes the first expert pack and the worked example.

Test tools decide how far Explore can go. With strong tools, ideas can end as tested or refuted. Without them, Explore still proposes ideas, but they stay labelled untested, and the report says what test would settle each one.

## Trust layer

Every claim in a report carries one label, and the label shows what evidence stands behind it. This is what lets a non-expert use the report safely.

| Label | Meaning | Evidence required |
|---|---|---|
| Established | Independent sources agree | 2+ sources, each passage quoted |
| Reported | One source says so | 1 source, passage quoted |
| Contested | Sources disagree | Both sides quoted |
| New idea: tested | Proposed here, passed a test | Script + output, reproduced by a second agent |
| New idea: refuted | Proposed here, failed a test | The counterexample or failing output |
| New idea: untested | Proposed here, no check run | Reasoning only, plus the test that would settle it |

Rules every role follows:

1. Never give a claim a stronger label than its evidence.
2. Cite only a saved source, with the passage quoted.
3. A command's output outranks any agent's report.
4. Never soften a question or claim to make it pass; record the failure.
5. Say "not found in the sources read," never "new" or "first."
6. On medical, legal or financial topics, say the report is research, not advice.

Automatic checks before a label is set:

| Check | Rule | Catches |
|---|---|---|
| Quote check | The quoted passage exists in the saved source and supports the claim | Made-up or stretched citations |
| Held-out | Tests re-run on new instances and seeds | Results fitted to the answer |
| Replication | A second agent with a separate brief reproduces any headline number | Flukes, scale errors |
| Like-for-like | Compared numbers share units and baselines | Inflated comparisons |
| Provenance | Every number links to a source or a log | Invented results |

These checks come from the failures in the Background table. Expert packs can add field-specific ones.

## Repository layout

One package. A user runs one command with a question; each question gets its own project folder, which keeps everything needed to audit or continue it.

```
gauntlet/
  core/
    orchestrator.md        # the loop, depth modes, stop conditions
    roles/                 # reader, synthesizer, ideator, prover, breaker, referee, writer
    rules.md               # trust rules, included in every role
  checks/                  # quote_check.py, held_out.py, replication.py, provenance.py
  profiles/                # topic-profile templates by field
  packs/                   # optional expert packs; quantum-readout is the example
  cli/                     # gauntlet ask, continue, status, report

projects/<question-slug>/  # created per question
  profile.md               # topic profile (editable)
  sources/                 # saved sources + quoted passages
  evidence_map.md          # agree / disagree / gaps
  ideas.md                 # every idea, its test and its label
  claims.jsonl             # every claim, label, evidence links
  runs/                    # scripts and logs per agent
  report.md                # plain-language answer + expert appendix
```

Example use:

```
gauntlet ask "Can quantum computers speed up fluid simulation?" --depth standard
```

Key formats:

- `claims.jsonl`: one line per claim with statement, label, sources (id + quoted passage), tests (script + log paths) and checks_passed. A label cannot be set unless its required checks passed.
- `ideas.md`: each idea with where it came from (which gap), the test proposed, the result and the label.
- `report.md`: the answer first, then findings by label, then new ideas, then what was not checked.

## Evaluation

Gauntlet works if its reports are accurate, its labels are honest, and ordinary users can run it. Six tests:

| Test | How | Pass |
|---|---|---|
| Citation accuracy | Sample 100 claims; check each quote exists and supports the claim | ≥ 95% |
| Label honesty | Field experts check claims labelled Established and New idea: tested | ≥ 95% hold up |
| Planted errors | Seed 10 false claims into sources or ideas | ≥ 9 caught |
| Answer quality | 30 questions across 6 fields; experts grade blind against a plain chatbot answer | Preferred in ≥ 2/3 |
| Replay | Run the quantum-readout question from scratch | Finds both PhysicsC191A results; known errors end refuted |
| Usability | 10 non-experts each run a question and explain the report back | 8 of 10 succeed unaided |

Track per run: time, cost by model tier, claims by label, and claims a person later overturned. The last number matters most.

## Risks, open questions and milestones

Risks:

| Risk | Mitigation |
|---|---|
| Users over-trust a polished report | A label on every claim; a "what was not checked" section in every report |
| Untested ideas read as findings | Ideas sit in their own section, never in the answer summary unless tested |
| Made-up or stretched citations | Quote check against the saved source before any label |
| High-stakes topics (health, law, money) | Not-advice notice; Established label needs systematic reviews or official sources |
| Paywalled sources | Open-access first; a paywalled source is listed as unread, never cited |
| Referee shares the agents' blind spots | Fresh brief, its own code, a different model family where possible |
| Cost surprises | Estimate shown before the run; hard budget per depth mode |

Open questions:

- What should Quick and Standard modes cost, and is that low enough for students?
- How should the report adapt to reading level: one setting, or inferred from the question?
- Which runner to support first: Claude Code, opencode, or a plain Python CLI?
- What disclosure line should go on reports that are shared or published?

Milestones:

1. Quick mode. Scope, Survey, Synthesize and Report with quote checks; no idea testing.
2. Trust layer. Labels, claims.jsonl, provenance and the "not checked" section.
3. Explore and Check. Ideator, Prover, Breaker and Referee; held-out and replication checks.
4. Topic profiles. Auto-generated profiles for the five field families; the quantum-readout expert pack.
5. Evaluation. Run the six tests; fix what fails.
6. Public release. README, three worked examples in different fields, disclosure guidance.
