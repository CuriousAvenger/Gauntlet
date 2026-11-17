# Known mistakes in this area

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

## Field-specific rules

- A lower bound is labelled tested only if the test or proof covers *every*
  readout strategy in the stated model, not a list of known ones.
- Shot counts and speedups are compared at the same condition number κ, target
  precision ε, problem size and baseline estimator.
- Gate and query counts come from the circuit actually built by the test script.
