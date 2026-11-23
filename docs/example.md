# Worked example

A short run on a **toy source** (one made-up sentence, saved with `--text-file`), to show
what each script does. The outputs are real; long ones are trimmed. In a real run the agent
reads real papers and its subagents play the roles.

Question in `AGENTS.md`: *Does importance-weighted readout reduce measurement cost?*

## Read a source

```
$ python3 .skills/gauntlet/scripts/source.py https://example.org/toy-paper --text-file toy.txt --title 'Toy readout paper'
{"source": "S1", "title": "Toy readout paper", "chars": 186}
```

## Record a claim: an inflated number is caught

```
$ echo '{"statement": "Shots fell 11-fold.", "quotes": [{"url": "https://example.org/toy-paper",
        "quote": "the number of shots needed to reach precision 0.01 fell by a factor of 8.0"}]}' | python3 .skills/gauntlet/scripts/claim.py
{"id": "C1", "label": "pending", "fix": ["the number 11 is not in any quote or test log"]}

$ python3 .skills/gauntlet/scripts/label.py C1 reported --reason 'one source states it'
{"id": "C1", "refused": "reported", "label": "Pending", "missing": ["the number 11 is not in any quote or test log"]}
```

The honest version earns its label:

```
$ echo '{"statement": "Shots fell 8-fold at precision 0.01.", "quotes": [...same quote...]}' | python3 .skills/gauntlet/scripts/claim.py
{"id": "C2", "label": "pending"}

$ python3 .skills/gauntlet/scripts/label.py C2 reported --reason 'one source states it'
{"id": "C2", "label": "Reported"}
```

## Propose and test an idea

An idea is grounded by quoting its closest prior work and stating what it adds:

```
$ echo '{"statement": "Updating the importance weights between batches cuts shots further.",
        "settling_test": "shots to precision 0.01 on 20 random systems",
        "prior_work": [{"url": "https://example.org/toy-paper", "quote": "the number of shots needed to reach precision 0.01 fell by a factor of 8.0"}],
        "difference": "the weights adapt during measurement", "lens": "statistics"}' | python3 .skills/gauntlet/scripts/claim.py
{"id": "I1", "label": "untested"}
```

Gauntlet runs the test itself, on the author's seed and on three it picks:

```
$ python3 .skills/gauntlet/scripts/run_test.py I1 support test.py --seeds 0
{"test": "I1-T1", "runs": [{"seed": 0, "held_out": false, "pass": true, "headline": {"extra_reduction": 1.534}},
                           {"seed": 59030012, "held_out": true, "pass": true, "headline": {"extra_reduction": 1.526}}, ...]}

$ python3 .skills/gauntlet/scripts/run_test.py I1 replication replica.py --replicates I1-T1
{"test": "I1-T2", "runs": [...all pass, extra_reduction 1.47–1.53...]}

$ python3 .skills/gauntlet/scripts/label.py I1 tested --reason 'held-out runs and replication agree'
{"id": "I1", "label": "New idea: tested"}
```

With several ideas, judges would compare them with `rank.py pairs` and `rank.py match`, and
the next generation would evolve the diverse top from `rank.py top`.

## Report

```
$ python3 .skills/gauntlet/scripts/report.py --answer answer.md
```

```markdown
# Does importance-weighted readout reduce measurement cost?

## Answer
One toy source reports an 8-fold drop in shots [C2 · Reported].

## Findings
### Reported
- **C2** Shots fell 8-fold at precision 0.01. _(S1)_

## New ideas
### New idea: tested
- **I1** Updating the importance weights between batches cuts shots further.

## What was not checked
- Claims that earned no label, left out above: C1.
...
```
