---
name: sympy
description: Use this skill when working with symbolic mathematics in Python. Covers symbolic algebra, calculus (derivatives, integrals, limits, series), equation solving (algebraic, linear, nonlinear, ODE), matrices and linear algebra, physics (mechanics, quantum, vectors, units), number theory, combinatorics, geometry, statistics, special functions, and code generation (lambdify, C/Fortran/LaTeX). Includes a specialized procedure for converting floating-point coordinates to exact rational fractions with a bounded denominator using `Rational.limit_denominator(N)` — the core sympy pattern needed for crystallographic Wyckoff position analysis (paired with pymatgen for CIF parsing and space-group symmetry). Apply when the user needs exact symbolic results rather than numerical approximations, when manipulating mathematical formulas with variables, or when extracting exact fractions from CIF / X-ray-diffraction-derived crystal-structure data.
license: https://github.com/sympy/sympy/blob/master/LICENSE
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  skill-author: K-Dense Inc.
  aip-conversion: zach-blumenfeld
---

```yaml
purpose: >
  Perform exact symbolic mathematics with SymPy. Define symbols (with
  appropriate assumptions), manipulate and simplify expressions, perform
  calculus and linear algebra, solve equations symbolically, and convert
  results into the format the caller needs — including exact rational
  approximations of floating-point inputs (`Rational.limit_denominator(N)`),
  which is the core pattern for crystallographic Wyckoff coordinate analysis.

trigger_when:
  - User asks to solve an equation, integrate, differentiate, take a limit, or expand a series symbolically.
  - User asks for an exact answer ("`sqrt(2)`, not `1.414…`", "rational fraction, not float").
  - User needs to manipulate or simplify an algebraic expression containing variables/parameters.
  - User asks for matrix / linear-algebra work that should remain symbolic (eigenvalues, characteristic polynomial, RREF, nullspace).
  - User needs physics modeling (Lagrangian / Kane mechanics, vector frames, quantum operators, units).
  - User needs to convert floats to exact fractions with a bounded denominator (`Rational(x).limit_denominator(N)`).
  - User is analyzing a CIF file for Wyckoff position multiplicities or exact fractional coordinates.
  - User asks to generate executable numerical code (`lambdify`, `codegen`) or LaTeX from a symbolic expression.

do_not_use_when:
  - The work is purely numerical / floating-point — NumPy or SciPy is the right tool, not SymPy.
  - The user wants visualization (defer to Matplotlib / Plotly; SymPy is the math engine, not the renderer).
  - The user asks for crystallographic analysis that does NOT need exact arithmetic (use pymatgen alone).

scope_and_approval: >
  Read-only by default: defining symbols, manipulating expressions, and
  printing results require no approval. Writing solution files (e.g., to
  `/root/workspace/solution.py`), running long symbolic computations, and
  installing additional packages are write actions — proceed when the task
  explicitly requests them.

steps:
  - name: classify-problem
    description: >
      Identify the category of symbolic-math work (algebra, calculus, ODE,
      matrices, physics, code generation, rationalization / Wyckoff) and the
      exact output format the caller expects. Cite the matching reference
      file the agent will load in later steps.
    outputs:
      - name: problem-category
        type: string
        description: One of `algebra`, `calculus`, `solve-eq`, `matrices`, `physics`, `code-gen`, `rationalize`, `wyckoff`, or `other`.
      - name: output-spec
        type: object
        description: What the caller expects back — return type, container shape, fraction-vs-float, denominator cap if any.

  - name: load-reference
    description: >
      Load only the reference file(s) relevant to `problem-category`.
      `references/core-capabilities.md` for algebra / calculus / solving;
      `references/matrices-linear-algebra.md` for matrices;
      `references/physics-mechanics.md` for mechanics / quantum / units;
      `references/advanced-topics.md` for number theory / combinatorics / geometry / statistics / polynomials;
      `references/code-generation-printing.md` for `lambdify` / `codegen` / LaTeX;
      `references/crystallography-wyckoff.md` for CIF / Wyckoff analysis.
      Skip references that don't apply — progressive disclosure keeps context lean.
    depends_on: [classify-problem]
    inputs:
      - name: problem-category
        type: string

  - name: define-symbols
    description: >
      Declare every variable with `sympy.symbols(...)` BEFORE using it.
      Add assumptions (`real`, `positive`, `integer`, `rational`, …) when
      they tighten simplification or rule out unwanted branches. Use
      `sympy.Rational(n, d)` or `sympy.S(n)/d` for exact constants — never
      `0.5` or other floats (those infect downstream results with
      floating-point error).
    inputs:
      - name: problem-category
        type: string
    outputs:
      - name: symbol-context
        type: object
        description: The symbols, assumptions, and exact constants that will be reused downstream.

  - name: compute
    description: >
      Run the symbolic computation. Pick the right primitive:
      `simplify`, `expand`, `factor`, `cancel`, `trigsimp` for expression manipulation;
      `diff`, `integrate`, `limit`, `series` for calculus;
      `solveset` / `solve` / `linsolve` / `nonlinsolve` / `dsolve` for equations;
      `Matrix` methods for linear algebra;
      `sympy.physics.*` for physics;
      `lambdify` / `codegen` / `latex` for outputs.
      Keep results symbolic — defer `evalf()` and rationalization until the
      format-output step.
    depends_on: [define-symbols, load-reference]
    inputs:
      - name: symbol-context
        type: object
    outputs:
      - name: symbolic-result
        type: object
        description: A SymPy expression, set, matrix, dict, or container of any of these.

  - name: rationalize-coordinates
    description: >
      Specialized step for Wyckoff-style coordinate output. Convert each
      floating-point coordinate to an exact `Rational` with a bounded
      denominator and serialize as a fraction string ("1/2", "2/3", "0").
      Use exactly the denominator cap the task specifies — do not invent
      one. Backed by a script so the cap is a parameter, not prose.
    depends_on: [compute]
    script: scripts/rationalize_coordinates.py
    inputs:
      - name: float-values
        type: list[float]
      - name: max-denominator
        type: integer
        description: Upper bound for the fraction denominator (e.g. 12 for typical crystallographic coordinates).
    outputs:
      - name: fraction-strings
        type: list[string]

  - name: wyckoff-pipeline
    description: >
      End-to-end CIF → Wyckoff multiplicities + exact-fraction coordinates.
      Reads the CIF with `pymatgen.Structure.from_file`, runs
      `SpacegroupAnalyzer.get_symmetry_dataset()` (attribute access:
      `dataset.wyckoffs`), counts multiplicities per letter, and rationalizes
      the representative atom's `frac_coords` with the supplied denominator
      cap. Returns the two-sub-dict shape required by the task spec.
      Use this step for the host task `crystallographic-wyckoff-position-analysis`;
      skip it for pure-symbolic-math tasks.
    depends_on: [load-reference]
    script: scripts/wyckoff_analyze.py
    inputs:
      - name: cif-filepath
        type: string
      - name: max-denominator
        type: integer
    outputs:
      - name: wyckoff-result
        type: object
        description: '{wyckoff_multiplicity_dict: {letter -> int}, wyckoff_coordinates_dict: {letter -> [str, str, str]}}'

  - name: validate
    description: >
      Sanity-check the result before returning. For equations, substitute
      solutions back and confirm the residual is zero (use `simplify`,
      not `==`). For Wyckoff output, confirm both sub-dicts are sorted by
      letter, coordinates are 3-element lists of strings, and multiplicities
      are positive ints. For numeric work derived from symbolic, sanity-check
      against `evalf()` magnitudes.
    depends_on: [compute, rationalize-coordinates, wyckoff-pipeline]
    inputs:
      - name: symbolic-result
        type: object
      - name: output-spec
        type: object

  - name: format-output
    description: >
      Convert the validated result to the exact return shape the caller
      requested: dict, list, string, LaTeX, executable function via
      `lambdify`, etc. For Wyckoff tasks the shape is fixed (two sub-dicts);
      for code-generation tasks, hand back the source string or callable.
    depends_on: [validate]
    inputs:
      - name: symbolic-result
        type: object
      - name: output-spec
        type: object
    outputs:
      - name: deliverable
        type: object

modes:
  - name: inline
    body: >
      For one-off symbolic computations (single integral, single solve call):
      run the steps inline in a REPL or notebook. No script file needed.

  - name: solution-file
    body: >
      For host tasks that demand a file at a specific path (e.g.
      `/root/workspace/solution.py`): import from `scripts/` or copy the
      logic into the required file. Keep the entry-function signature exactly
      as the task instructs.

search_shortcuts:
  - category: Symbolic computation
    body: >
      `sympy.symbols`, `sympy.Symbol`, `simplify`, `expand`, `factor`,
      `cancel`, `trigsimp`, `Rational`, `S`, `evalf`.

  - category: Calculus
    body: >
      `diff`, `integrate`, `limit`, `series`, `Derivative`, `Integral`, `oo`.

  - category: Equation solving
    body: >
      `solveset`, `solve`, `linsolve`, `nonlinsolve`, `dsolve`, `roots`,
      `real_roots`, `nsolve`.

  - category: Linear algebra
    body: >
      `Matrix`, `eye`, `zeros`, `ones`, `diag`, `Matrix.det`, `Matrix.inv`,
      `Matrix.eigenvals`, `Matrix.eigenvects`, `Matrix.diagonalize`,
      `Matrix.rref`, `Matrix.nullspace`, `Matrix.LUdecomposition`.

  - category: Crystallography (paired libraries)
    body: >
      `pymatgen.core.Structure.from_file` for CIF parsing;
      `pymatgen.symmetry.analyzer.SpacegroupAnalyzer.get_symmetry_dataset`
      for Wyckoff letters (access via `dataset.wyckoffs`, attribute not key);
      `sympy.Rational(x).limit_denominator(N)` for bounded-denominator
      rationalization of float coordinates.

  - category: Code generation & printing
    body: >
      `lambdify`, `sympy.utilities.codegen.codegen`, `latex`, `pretty`,
      `pprint`, `srepr`, `autowrap`, `ufuncify`.

integrations:
  - partner: pymatgen
    body: >
      Pair with `pymatgen` for crystallography: pymatgen parses CIF files,
      runs space-group symmetry analysis, and exposes Wyckoff letters and
      fractional coordinates; SymPy converts the floating-point fractional
      coordinates to exact rationals. The two libraries are tightly coupled
      for the host task `crystallographic-wyckoff-position-analysis`.

  - partner: numpy
    body: >
      Use `lambdify(syms, expr, "numpy")` to turn a symbolic expression into
      a vectorized NumPy callable for high-throughput numerical evaluation.
      `Rational` and `Symbol` interoperate with NumPy scalars when wrapped.

  - partner: scipy
    body: >
      For root-finding or optimization that SymPy can't close-form, lambdify
      the expression and hand off to `scipy.optimize.fsolve` /
      `scipy.optimize.minimize`.

scenarios:
  - need: Solve a quadratic equation and verify the solutions.
    context: User wants exact roots, not floats.
    action: >
      Define `x = symbols('x')`; call `solve(x**2 - 5*x + 6, x)` → `[2, 3]`;
      substitute each root back via `simplify(eq.subs(x, sol))` to confirm 0.
    outcome: Exact integer roots returned; verification confirms correctness.

  - need: Extract Wyckoff multiplicities and exact fractional coordinates from a CIF.
    context: >
      Task spec says "constrain fractions to have denominators ≤ 12". CIF
      lives at `/root/cif_files/FeS2_mp-226.cif`.
    action: >
      Call `scripts/wyckoff_analyze.py analyze_wyckoff(filepath, max_denominator=12)`
      (or replicate the pattern inline). It loads with
      `pymatgen.Structure.from_file`, runs `SpacegroupAnalyzer`, reads
      `dataset.wyckoffs` by attribute, counts multiplicities with
      `collections.Counter`, and rationalizes each first-site `frac_coords`
      with `sympy.Rational(c).limit_denominator(12)`.
    outcome: >
      `{"wyckoff_multiplicity_dict": {"a": 4, "c": 8},
        "wyckoff_coordinates_dict": {"a": ["0", "1/2", "1/2"], "c": ["3/8", "1/9", "8/9"]}}`

  - need: Convert a series of decimal coordinates to fraction strings.
    context: Coordinates from any source where exact rationals matter.
    action: >
      `rationalize([0.0, 0.333333, 0.875], max_denominator=12)` →
      `["0", "1/3", "7/8"]`. The helper is library-agnostic — any float input
      works.
    outcome: Clean fraction strings ready to embed in test fixtures or output dicts.

  - need: Symbolically integrate `x**2 * exp(-x)` from 0 to ∞.
    action: >
      `x = symbols('x', positive=True); integrate(x**2 * exp(-x), (x, 0, oo))` → `2`.
    outcome: Closed-form exact answer (no numerical quadrature needed).

  - need: Turn a symbolic expression into a fast NumPy function.
    action: >
      `f = lambdify(x, sin(x) / x, "numpy")`; call `f(np.linspace(-10, 10, 1000))`.
    outcome: Vectorized callable, orders of magnitude faster than `subs+evalf` in a loop.

anti_patterns:
  - Using Python floats like `0.5` instead of `Rational(1, 2)` or `S(1)/2` — every downstream simplification then carries floating-point noise.
  - Treating the spglib symmetry dataset as a dict (`dataset["wyckoffs"]`). It's a dataclass; use attribute access (`dataset.wyckoffs`).
  - Calling `str(Rational(0.333333))` without `.limit_denominator(N)` — produces a 16-digit denominator nightmare instead of `1/3`.
  - Inventing a denominator cap. Use exactly what the task specifies; higher caps fabricate spurious fractions and lower caps lose detail.
  - Returning SymPy `Rational` objects when the spec asks for strings — serialize with `str(rat)` for canonical "n/d" form.
  - Forgetting to sort output dicts by Wyckoff letter — equality tests will fail on key order in some agents.
  - Hardcoding answers for known CIF files. The function must be a generic transform of any CIF input.
  - Reaching for `subs()` at a singularity instead of `limit()` — `subs` returns `nan` or `zoo`; `limit` tracks growth rates correctly.
  - Loading all five reference files at activation. Load only the one that matches the classified problem category.
  - Promoting unrelated marketing prose into the activated body — the curated source skill's trailing K-Dense suggestion was deliberately dropped on conversion.
```
