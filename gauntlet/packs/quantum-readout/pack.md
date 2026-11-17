---
name: quantum-readout
field: math-physics-cs
origin: PhysicsC191A (quantum linear-system readout)
---
# Expert pack: quantum linear-system readout

This pack carries what the PhysicsC191A run learned about researching readout
(measurement) costs for quantum linear-system solvers. It is the worked example
for expert packs: seed sources, test conventions, the mistakes that run made,
and notation. It is included in every role's brief when a project uses it.

Sections below: seed sources, known mistakes, how ideas are tested, notation.

## Replay target

Running the quantum-readout question from scratch should:

1. find both results from PhysicsC191A that survived checks and were not found
   by search (the shot-reduction result on the fluid-solver experiment, with
   three independent replications at 8.51×, 8.21× and 7.99× fewer shots);
2. end with every known error from that run labelled refuted or never labelled
   (see Known mistakes).
