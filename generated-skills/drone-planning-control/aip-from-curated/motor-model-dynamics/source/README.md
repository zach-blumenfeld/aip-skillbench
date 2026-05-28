# motor-model-dynamics — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `motor-model-dynamics`
from the `drone-planning-control` SkillsBench task (`aip-from-curated`
track). The canonical original is preserved verbatim at
`source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.
- Cross-referenced (for context only, not bundled): the task's
  `instruction.md`, `system_params.yaml`, sibling skills
  (`position-controller-trajectory-planner`, `attitude-controller-planner`,
  `flight-plan-parser`, `plot-quadrotor`, `stepinfo-3d`), and the
  oracle solution at `solution/solve.sh` which confirms the
  motor-model + dynamics layout (4x4 allocation matrix, first-order
  lag, 16-state ZYX-Euler equations of motion).

## Schema choice

`procedure` schema (reused, not drafted). The physics layer is a
deterministic execution graph: load params -> derive thrust envelope
-> motor step -> dynamics step -> integrate one timestep. Exactly
what the procedure schema models.

## Why these scripts exist

Per AIP best practice, anything with fixed math, lookup tables,
numeric thresholds, or matrix structure belongs in `scripts/`:

- `scripts/motor_model.py` — the 4x4 X-frame allocation matrix
  (rows/columns determined by `cT`, `cQ`, `d`), the allocation solve
  with the clamp-then-sqrt-then-clip ordering, the first-order lag,
  the `F_actual` / `M_actual` computation from current RPMs, and the
  derived thrust-envelope quantities (T_max, T_min, twr,
  accel_up_max, accel_down_max). The original presented these as a
  prose table; scripting them lets the agent call them
  deterministically and surfaces the ordering bugs the anti-patterns
  list calls out.
- `scripts/dynamics.py` — the 16-element state derivative and the
  ZYX Euler trigonometry for the velocity derivative. The original
  spelled out the formulas in prose; the script encodes them once so
  the integrator and the agent agree on the contract.
- `scripts/integrate.py` — thin RK45 wrapper around `solve_ivp` so
  the integration method is one clear knob, and so the
  zero-order-hold contract for `F_actual`, `M_actual`, `rpm_dot` is
  visible in code rather than only described in prose.

No prose-only step survives in the body. Every logical action is
either script-backed or a one-shot setup/loading step.

## Notable expansions beyond the literal source

The curated `SKILL.md` is faithful to the intent but a few points the
agent needs to succeed are implicit. The AIP version surfaces them:

- **Clamp-before-sqrt ordering.** The curated text says "take `sqrt`
  of each element (clamp negatives to 0 first)" but does not
  emphasize that swapping the order (clipping squared values to
  `[rpm_min**2, rpm_max**2]` before `sqrt`) is a bug. Encoded as a
  script and called out in `anti_patterns`.
- **Zero-order hold on motor outputs across the RK45 step.** The
  original says `F_actual` and `M_actual` are "held constant for the
  step" — the AIP version names this as the zero-order-hold contract
  the integrator wrapper enforces, and flags recomputing them inside
  the ODE RHS as an anti-pattern.
- **`F_actual` from current (not desired) RPMs.** The original
  formula reads `prop_matrix @ (motor_rpm ** 2)`; the AIP version
  flags using the post-clip desired RPMs instead as a subtle bug
  that defeats the first-order lag.
- **`inertia` shape.** The original mentions `I^{-1} M` but doesn't
  say `inertia` must be a (3, 3) np.ndarray for `np.linalg.solve` to
  work. `load-system-params` now states the diag conversion
  explicitly, and `anti_patterns` flags the list-shape bug.
- **`envelope-only` mode.** The thrust envelope derivation is useful
  on its own (sizing `accel_limit_*` for a new airframe before
  integrating anything). Surfaced as a separate `modes` entry.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- Overview ("two modules: motor model + dynamics") -> **Mapped** to
  `purpose` plus the two clusters of steps (`motor-step`,
  `dynamics-step`).
- Propeller allocation matrix table -> **Mapped** to
  `compute-thrust-envelope` / `motor-step` descriptions and encoded
  in `scripts/motor_model.py` (`build_prop_matrix`).
- Motor model implementation logic (5 numbered steps: build matrix,
  solve for rpm_sq, sqrt+clip, first-order lag, actual force/moment)
  -> **Mapped** in `motor-step` and `scripts/motor_model.py`.
- State vector table (16 elements) -> **Mapped** in `purpose` and
  the docstring of `scripts/dynamics.py`.
- Dynamics implementation logic (5 numbered steps: position,
  velocity, Euler, angular vel, motor RPM derivatives, including
  the ZYX-Euler formulas) -> **Mapped** in `dynamics-step` and
  `scripts/dynamics.py`.
- RK45 integration ("scipy.integrate.solve_ivp with method='RK45'",
  zero-order hold of forces/moments, last-column extraction) ->
  **Mapped** in `integrate-step` and `scripts/integrate.py`.
- Motor physical limits table (rpm_min, rpm_max, motor_constant
  with tau interpretation) -> **Mapped** in `load-system-params`
  (read from `system_params.yaml`) and used numerically inside
  `motor_model.py` (the values themselves live in
  `system_params.yaml`, not duplicated in the skill — the original
  table was documentation of what `params` contains).
- Max thrust calculation block (T_max, T_min, twr, max upward
  accel, max downward accel) -> **Mapped** to
  `compute-thrust-envelope` and `thrust_envelope(...)` in
  `scripts/motor_model.py`.

No source content was dropped. Where the original used a prose table
(motor limits), the AIP version points at the canonical
`system_params.yaml` source rather than restating values that would
drift.

## Tested

The motor-model allocation solve, clamp-then-sqrt-then-clip,
first-order lag, and thrust-envelope derivation were exercised
against the bundled `system_params.yaml`. The envelope produced
matches `accel_limit_up = 6.962`, `accel_limit_down = 9.429`, and
the dynamics RHS matches the oracle solution's hand-inlined RK4
formulas (modulo integration method).
