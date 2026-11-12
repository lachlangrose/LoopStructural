# Specification index

Updated: 2026-11-04. This index records document and workflow state. It does
not certify that an implementation or a numerical acceptance gate passed.

| Spec | State | Next step or existing open point |
|---|---|---|
| [001-low-memory-interpolator](001-low-memory-interpolator/spec.md) | Spec declares ready for plan, reviewed 2026-10-27 | Follow its existing plan and task workflow. This cascade did not reassess it. |
| [002-rbf-interpolator](002-rbf-interpolator/spec.md) | Draft, not reviewed | Continue its existing review and clarification workflow. This cascade did not change it. |
| [003-fault-evaluation-performance](003-fault-evaluation-performance/spec.md) | Implementation in progress; 005 contract cascade applied | Its active plan and tasks remain in the existing LoopStructural-native worktree. OP3 and OP4 remain open; completed tasks, including concurrent T043, and measured failures are preserved. |
| [004-matrix-free-directional-constraints](004-matrix-free-directional-constraints/spec.md) | Draft; 005 contract cascade applied; task graph checked | Review the updated plan and tasks. OP1 still requires the quadrature measurements before a default is chosen. |
| [005-coordinate-frame-correctness](005-coordinate-frame-correctness/spec.md) | S1 implemented 2026-11-04 on `feat/005-coordinate-frame-correctness` (17 of 17 tasks; evidence in [verification.md](005-coordinate-frame-correctness/verification.md)); S5 planned 2026-11-05 and revised after review; S6 planned 2026-11-06 and reviewed the same day; maintainer decisions recorded ("Stage S6 design" in plan.md; OP1, OP18, OP19 and OP20 closed; spec clarification C-019 added; OP21 to OP24 have defaults and block no task) | Review and merge the S1 branch. S2 planned and tasked 2026-11-04 (T018 to T031, waves 8 to 13); run spec-orchestrator for S2. S3 planned and tasked 2026-11-05 ("Stage S3 design" in plan.md; OP4 and OP5 closed; T033 to T050, waves 14 to 22; build after S2 merges). S3 is built on `feat/005-s3-frame-persistence` (pull request #397, stacked on #396; 18 of 18 tasks, evidence in verification.md). S3 merged (#397); a follow-up keeps the legacy load backward compatible (pull request #400). S4 planned and tasked 2026-11-05 ("Stage S4 design" in plan.md; OP8 to OP10 have defaults and block nothing; T051 to T068, waves 23 to 31); run spec-orchestrator for S4. S5 planned 2026-11-05 and revised the same day after review and five maintainer answers ("Stage S5 design" in plan.md; OP13 to OP15 closed; OP12, OP16 and OP17 have defaults; OP17 blocks the S5 merge only if a parity file changes); S5 tasked 2026-11-05 (T069 to T088, waves 32 to 42; no open point blocks a task; build after S4 merges). OP1 closed 2026-11-06. S6 tasked 2026-11-06 (T089 to T108, waves 43 to 52; 20 tasks; no open point blocks a task; build after S5 merges). OP3: constant-norm accuracy check. OP2 closed 2026-11-04: the R2/R5 matrix stays in the default pytest run. 7 minor review findings are open (run-state.json). |
| [006-loop-link](006-loop-link/spec.md) | Draft, reviewed twice (2026-11-06); one open mark (story 7 scenario 7); plan written 2026-11-06 for stories 1 and 5 ([plan.md](006-loop-link/plan.md): stages S1 to S3) | Tasks written 2026-11-06 ([tasks.md](006-loop-link/tasks.md): 37 tasks, 13 waves, S1 to S3, no blocked task). Run spec-orchestrator for 006. OP6: plan S4 (stories 6, 7). OP7: plan S5 (stories 2 to 4) after geoviewer spec 066-selection-and-fetch lands. |
| [007-loop-skills](007-loop-skills/spec.md) | Draft, reviewed twice (2026-11-10); marks closed; plan written 2026-11-10 ([plan.md](007-loop-skills/plan.md): stages S1 to S4) | Tasks written 2026-11-10 ([tasks.md](007-loop-skills/tasks.md): 38 tasks, 13 waves, S1 to S4; T020 blocked by OP3, T034 blocked by OP2). Run spec-orchestrator for 007. OP1: decide the wording of SC-004. OP2 to OP4: check the plugin schema, the Codex folder and the Copilot size in the stage that needs them. OP5: confirm the re-install policy. |
| [008-loop-skills-faults](008-loop-skills-faults/spec.md) | Draft, being re-scoped to faults only (2026-11-11) | Finish the interview (fault reasoning workflow), then run spec-reviewer. Depends on 007. |
| [009-loop-skills-folds](009-loop-skills-folds/spec.md) | Stub (2026-11-11) | Interview after 008. Depends on 007 and 008. |

## Cascade of 005

The accepted coordinate contract keeps modelling observations, reference
geometry, masks, and public queries in world coordinates. Local assembly
and low-level core inputs use the computational frame. Each boundary
converts points and directions once.

Analytic evidence and explicit review may justify corrections to affected
golden results and fingerprints. Unaffected references, numeric bounds,
acceptance tolerances, and performance targets remain unchanged.

The cascade changes documents only. It does not update golden files,
benchmark data, solver code, or the run-state of an implementation.

The matching 003 spec copies in the main checkout and its active worktree
are kept in sync. Its plan and tasks are not copied into the main checkout.
The documentation changes create no whole-spec implementation dependency
between 005 and either target.
