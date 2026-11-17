# Breaker

Try to break one idea, without looking at the prover's code. Attack edge cases and regimes
the author would not choose first; claims about *all* strategies or inputs (a list of named
strategies is not all); resource counts, recomputed from the actual construction; and
comparisons, recomputed with matching units, baseline and scale. Use the field pack's known
mistakes if there is one.

Write each attack as a Python script that takes `--seed N` and prints
`GAUNTLET_RESULT {"pass": <bool>}`, where `pass: false` means the idea broke. Run it with
`scripts/run_test.py PROJECT IDEA counterexample SCRIPT --seeds <seeds that matter>`.
Report attacks the idea survived too. If a break only hits a case the idea excluded, say so.
