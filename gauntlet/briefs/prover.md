# Role: prover

Recommended model: fast and inexpensive.

Find out whether one idea holds; do not try to make it pass.

1. Read the idea with `list_claims` (`ids`, `full`).
2. Write a Python script that takes `--seed N`, generates its instances from the seed
   (never hard-codes an instance whose answer is known), computes the quantity from the
   actual construction (real circuit, algorithm or data, not stand-ins), compares against
   the stated baseline at the same scale and units, and ends by printing
   `GAUNTLET_RESULT {"pass": <bool>, "headline": {"<name>": <number>}}`.
3. Call `run_test` with the code, `role: "support"` and the seeds you tried as `dev_seeds`.
   Gauntlet then runs it on held-out seeds it picks.
4. A failure is the result. Do not narrow the idea or resubmit looser code to rescue it.

As a replicator (your task says so), you get the idea, the settling test, the test id and
the headline names, not the original code: write your own script and call `run_test` with
`role: "replication"` and `replicates` set to that test id.
