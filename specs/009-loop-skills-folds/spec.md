# Feature spec: loop-skills-folds, fold skill

**Feature**: `009-loop-skills-folds` | **Created**: 2026-11-11 | **Status**: Draft

**Input**: Add a fold skill (`add-folds`) to the `loop-skills` package. The
agent helps the user choose and fit the fold model: the fold frame, the fold
rotation angle profile fitted to the S-plot or fold normalisation, and
refolding. Depends on spec 007-loop-skills and 008-loop-skills-faults.

## Notes from spec 008 (to use in the interview)

- Split from the first draft of 008. The fold parts of that draft move here:
  fold frame, folded foliation, refolding (folded fold frame), fold tables in
  `map2loop-prepare`, fold listing in `inspect-model`.
- The skill must guide a modelling decision, not only run calls: fold profile
  fitted to the S-plot, or fold normalisation only.
- Same approach as 008: the agent uses the geological knowledge of the user
  and the observed data to refine the choice.

## User scenarios and tests

[NEEDS CLARIFICATION: start the interview for this spec]
