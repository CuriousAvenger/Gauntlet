# How ideas are tested here

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
