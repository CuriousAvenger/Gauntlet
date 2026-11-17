# Expert pack: quantum linear-system readout

This pack carries what the PhysicsC191A run learned about researching readout
(measurement) costs for quantum linear-system solvers. It is the worked example
for expert packs: seed sources, test conventions, the mistakes that run made,
and notation. Give it to every role when researching this area.

## Replay target

Running the quantum-readout question from scratch should:

1. find both results from PhysicsC191A that survived checks and were not found
   by search (the shot-reduction result on the fluid-solver experiment, with
   three independent replications at 8.51×, 8.21× and 7.99× fewer shots);
2. end with every known error from that run labelled refuted or never labelled
   (see Known mistakes).

## Seed sources

Readers read these first, then search outward from their references.

| Source | Why |
|---|---|
| arXiv:2610.08890 | Closest prior work found by review: the PhysicsC191A result is partly contained in it. The referee must quote it when judging whether an idea is already known. |

Add your own seeds below (one row per source, with an open-access URL where possible).
The original run downloaded 32 papers; list the ones you rely on here so a replay
starts from the same reading.

## Known mistakes

Each row is a failure from the PhysicsC191A run that review caught only late.
Breakers attack these first; referees check for them before labelling.

| Mistake | What happened | Check that catches it |
|---|---|---|
| Answer-fitted simulation | Circuit simulation tuned to the known answer | Held-out seeds chosen by Gauntlet when it runs the test |
| Fake resource counts | Gate counts taken from random unitaries | Recount from the actual circuit (breaker: resource recount) |
| False lower bounds (×3) | Proof covered named strategies only | "For all strategies" audit (breaker) |
| Scale mismatch | An 11.3× speedup was really ~8× | Referee and breaker recompute comparisons at matched units and scale |
| Novelty overclaim | Result partly in arXiv:2610.08890 | Referee quotes the closest paper; say "not found in the sources read" |
| Refuted claim left as PROVED | Ω(κ/ε²) stayed in the question list after refutation | Re-audit before every report: changed test code is re-run |

### Field-specific rules

- A lower bound is labelled tested only if the test or proof covers *every*
  readout strategy in the stated model, not a list of known ones.
- Shot counts and speedups are compared at the same condition number κ, target
  precision ε, problem size and baseline estimator.
- Gate and query counts come from the circuit actually built by the test script.

## How ideas are tested

- **Numerics on many instances.** Generate random linear systems with a seed
  (condition number κ and size n stated); never only the instance from the paper.
- **Shot counts:** estimate the number of measurement shots needed to reach
  precision ε for the target observable, for both the proposed readout and the
  baseline, on the same instances. Headline: `shot_reduction = baseline / proposed`.
- **Held-out:** run the same script on seeds the author did not use, including
  larger n and κ than in development.
- **Replication:** a second prover implements the readout from the idea's
  description alone. The PhysicsC191A fluid-solver result replicated three
  times at 8.51×, 8.21× and 7.99×; spreads of that size are within the default
  10% replication tolerance.
- **Resource counts:** count gates from the constructed circuit (e.g. by walking
  the circuit object), not from formulas or random unitaries.
- Test scripts end with
  `GAUNTLET_RESULT {"pass": ..., "headline": {"shot_reduction": ...}}`.

## Notation

| Symbol | Meaning |
|---|---|
| A, b | The linear system A x = b |
| κ (kappa) | Condition number of A |
| ε (epsilon) | Target precision of the estimated observable |
| n | Number of qubits / log of system size |
| N | System dimension (N = 2^n) |
| shots | Number of circuit repetitions (measurements) |
| Ω(·), O(·) | Asymptotic lower / upper bounds |
