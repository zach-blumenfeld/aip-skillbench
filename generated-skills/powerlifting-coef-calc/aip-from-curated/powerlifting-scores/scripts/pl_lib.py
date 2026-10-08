"""Powerlifting scoring formulas: Python reference implementations and matching
Excel formula builders. Constants, clamps and zero rules follow the OpenPowerlifting
Rust sources quoted in source/powerlifting/SKILL.md (Schwartz/Malone from
OpenPowerlifting's schwartzmalone module; see references/scoring-formulas.md).
"""

import math
import os
import re
import shutil
import subprocess
import sys


def ensure_openpyxl():
    """The task container ships openpyxl; elsewhere re-run this script once under
    `uv run --with openpyxl` so the step still works."""
    try:
        import openpyxl  # noqa: F401
        return
    except ImportError:
        pass
    uv = shutil.which("uv")
    if not uv or os.environ.get("PL_BOOTSTRAPPED"):
        sys.exit("openpyxl is required: pip install openpyxl (or install uv)")
    env = dict(os.environ, PL_BOOTSTRAPPED="1")
    r = subprocess.run([uv, "run", "--no-project", "--quiet", "--python", sys.executable, "--with", "openpyxl",
                        "python", os.path.abspath(sys.argv[0])], input=sys.stdin.read(), text=True,
                       capture_output=True, env=env)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    sys.exit(r.returncode)

SYSTEMS = ("dots", "wilks", "ipf_gl", "glossbrenner")

# ---------------------------------------------------------------- constants

DOTS = {
    "M": ((-0.0000010930, 0.0007391293, -0.1918759221, 24.0900756, -307.75076), 40.0, 210.0),
    "F": ((-0.0000010706, 0.0005158568, -0.1126655495, 13.6175032, -57.96288), 40.0, 150.0),
}
# Wilks polynomial A + Bx + Cx^2 + Dx^3 + Ex^4 + Fx^5
WILKS = {
    "M": ((-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-06, -1.291e-08), 40.0, 201.9),
    "F": ((594.31747775582, -27.23842536447, 0.82112226871, -0.00930733913, 0.00004731582, -0.00000009054), 26.51, 154.53),
}
# IPF GL (A, B, C) by (event, sex, equipment group)
IPF_GL = {
    ("SBD", "M", "Raw"): (1199.72839, 1025.18162, 0.009210),
    ("SBD", "M", "Single"): (1236.25115, 1449.21864, 0.01644),
    ("SBD", "F", "Raw"): (610.32796, 1045.59282, 0.03048),
    ("SBD", "F", "Single"): (758.63878, 949.31382, 0.02435),
    ("B", "M", "Raw"): (320.98041, 281.40258, 0.01008),
    ("B", "M", "Single"): (381.22073, 733.79378, 0.02398),
    ("B", "F", "Raw"): (142.40398, 442.52671, 0.04724),
    ("B", "F", "Single"): (221.82209, 357.00377, 0.02937),
}
GL_RAW = ("Raw", "Wraps", "Straps")
GL_SINGLE = ("Single-ply", "Multi-ply", "Unlimited")
SCHWARTZ_POLY = (0.631926e1, -0.262349, 0.511550e-2, -0.519738e-4, 0.267626e-6, -0.540132e-9, -0.728875e-13)
SCHWARTZ_TAIL = ((136, 0.5210, 0.0012, 125), (146, 0.5090, 0.0011, 135), (156, 0.4980, 0.0010, 145))
SCHWARTZ_LAST = (0.4879, 0.0009, 155)
MALONE = (106.011586323613, -1.293027130579051, 0.322935585328304, 29.24)
GLOSS_M = (153.05, -0.000821668402557, 0.676940740094416)
GLOSS_F = (106.3, -0.000313738002024, 0.852664892884785)


# ---------------------------------------------------------------- python reference

def num(v):
    """Excel-like numeric value of a referenced cell: blank -> 0, numeric text -> float."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return 0.0


def dichot(sex):
    return "F" if str(sex or "").strip().upper() == "F" else "M"


def clamp(x, lo, hi):
    return min(max(x, lo), hi)


def dots_coef(sex, bw):
    (a, b, c, d, e), lo, hi = DOTS[dichot(sex)]
    x = clamp(bw, lo, hi)
    return 500.0 / (a * x**4 + b * x**3 + c * x**2 + d * x + e)


def wilks_coef(sex, bw):
    k, lo, hi = WILKS[dichot(sex)]
    x = clamp(bw, lo, hi)
    return 500.0 / sum(k[i] * x**i for i in range(6))


def schwartz_coef(bw):
    x = max(bw, 40.0)
    if x <= 126:
        return sum(SCHWARTZ_POLY[i] * x**i for i in range(7))
    for hi, base, slope, off in SCHWARTZ_TAIL:
        if x <= hi:
            return base - slope * (x - off)
    base, slope, off = SCHWARTZ_LAST
    return base - slope * (x - off)


def malone_coef(bw):
    a, b, c, lo = MALONE
    return a * max(bw, lo) ** b + c


def gloss_coef(sex, bw):
    if dichot(sex) == "M":
        cut, a, b = GLOSS_M
        return (schwartz_coef(bw) + (wilks_coef("M", bw) if bw < cut else a * bw + b)) / 2.0
    cut, a, b = GLOSS_F
    return (malone_coef(bw) + (wilks_coef("F", bw) if bw < cut else a * bw + b)) / 2.0


def gl_params(sex, equipment, event):
    eq = str(equipment or "").strip()
    grp = "Raw" if eq in GL_RAW else "Single" if eq in GL_SINGLE else None
    ev = str(event or "").strip().upper()
    return IPF_GL.get((ev, dichot(sex), grp), (0.0, 0.0, 0.0))


def points(system, sex, bw, total, equipment=None, event=None):
    bw, total = num(bw), num(total)
    if system == "ipf_gl":
        a, b, c = gl_params(sex, equipment, event)
        if a == 0.0 or bw < 35 or total == 0:
            return 0.0
        den = a - b * math.exp(-c * bw)
        if den == 0:
            return 0.0
        return total * max(0.0, 100.0 / den)
    if bw == 0 or total == 0:
        return 0.0
    coef = {"dots": dots_coef, "wilks": wilks_coef, "glossbrenner": gloss_coef}[system](sex, bw)
    return coef * total


def excel_round(x, n):
    if n is None:
        return x
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- excel builders

def f(x):
    return repr(float(x)).replace("e-0", "E-").replace("e-", "E-").replace("e+", "E+")


def _poly_desc(k, x):
    # A*x^4 + B*x^3 + ... with k given highest power first
    n = len(k) - 1
    parts = []
    for i, c in enumerate(k):
        p = n - i
        term = f(c) if p == 0 else f"{f(c)}*{x}" if p == 1 else f"{f(c)}*{x}^{p}"
        parts.append(term)
    return "+".join(parts).replace("+-", "-")


def _poly_asc(k, x):
    return _poly_desc(list(reversed(k)), x)


def _clamp(x, lo, hi):
    return f"MIN(MAX({x},{f(lo)}),{f(hi)})"


def _is_f(sex):
    return f'{sex}="F"'


def x_dots(sex_r, bw, tot):
    (km, lom, him), (kf, lof, hif) = DOTS["M"], DOTS["F"]
    den = f"IF({_is_f(sex_r)},{_poly_desc(kf, _clamp(bw, lof, hif))},{_poly_desc(km, _clamp(bw, lom, him))})"
    return f"IF(OR({bw}=0,{tot}=0),0,{tot}*500/{den})"


def _wilks_coef_x(k, lo, hi, bw):
    return f"500/({_poly_asc(k, _clamp(bw, lo, hi))})"


def x_wilks(sex_r, bw, tot):
    m, w = WILKS["M"], WILKS["F"]
    return f"IF(OR({bw}=0,{tot}=0),0,{tot}*IF({_is_f(sex_r)},{_wilks_coef_x(*w, bw)},{_wilks_coef_x(*m, bw)}))"


def _schwartz_x(bw):
    x = f"MAX({bw},40)"
    poly = _poly_asc(SCHWARTZ_POLY, x)
    tail = f"{f(SCHWARTZ_LAST[0])}-{f(SCHWARTZ_LAST[1])}*({x}-{SCHWARTZ_LAST[2]})"
    for hi, base, slope, off in reversed(SCHWARTZ_TAIL):
        tail = f"IF({x}<={hi},{f(base)}-{f(slope)}*({x}-{off}),{tail})"
    return f"IF({x}<=126,{poly},{tail})"


def _malone_x(bw):
    a, b, c, lo = MALONE
    return f"({f(a)}*MAX({bw},{f(lo)})^({f(b)})+{f(c)})"


def x_gloss(sex_r, bw, tot):
    cm, am, bm = GLOSS_M
    cf, af, bf = GLOSS_F
    men = f"({_schwartz_x(bw)}+IF({bw}<{f(cm)},{_wilks_coef_x(*WILKS['M'], bw)},{f(am)}*{bw}+{f(bm)}))/2"
    women = f"({_malone_x(bw)}+IF({bw}<{f(cf)},{_wilks_coef_x(*WILKS['F'], bw)},{f(af)}*{bw}+{f(bf)}))/2"
    return f"IF(OR({bw}=0,{tot}=0),0,{tot}*IF({_is_f(sex_r)},{women},{men}))"


def x_ipf_gl(sex_r, bw, tot, eq_r, ev_r):
    # lookup key = event & sex group & equipment group, e.g. "SBDMR"; unknown -> no match -> 0
    raw = "OR(" + ",".join(f'{eq_r}="{e}"' for e in GL_RAW) + ")"
    single = "OR(" + ",".join(f'{eq_r}="{e}"' for e in GL_SINGLE) + ")"
    key = f'{ev_r}&IF({_is_f(sex_r)},"F","M")&IF({raw},"R",IF({single},"S","X"))'
    keys = list(IPF_GL)
    klist = "{" + ",".join(f'"{ev}{sx}{eq[0]}"' for ev, sx, eq in keys) + "}"

    def param(i):
        vals = "{" + ",".join(f(IPF_GL[k][i]) for k in keys) + "}"
        return f"IFERROR(INDEX({vals},MATCH({key},{klist},0)),0)"

    a, b, c = param(0), param(1), param(2)
    den = f"({a}-{b}*EXP(-{c}*{bw}))"
    return f"IF(OR({a}=0,{bw}<35,{tot}=0),0,IF({den}=0,0,{tot}*MAX(0,100/{den})))"


def score_formula(system, refs):
    if system == "dots":
        return x_dots(refs["sex"], refs["bodyweight"], refs["total"])
    if system == "wilks":
        return x_wilks(refs["sex"], refs["bodyweight"], refs["total"])
    if system == "glossbrenner":
        return x_gloss(refs["sex"], refs["bodyweight"], refs["total"])
    if system == "ipf_gl":
        return x_ipf_gl(refs["sex"], refs["bodyweight"], refs["total"], refs["equipment"], refs["event"])
    raise ValueError(f"unknown score system {system!r}; supported: {', '.join(SYSTEMS)}")


# ---------------------------------------------------------------- misc helpers

CANON = {
    "name": ["name", "lifter", "athlete"],
    "sex": ["sex", "gender"],
    "bodyweight": ["bodyweightkg", "bodyweight", "bwt", "bw", "weightkg"],
    "squat": ["best3squatkg", "squat", "bestsquat", "squatkg"],
    "bench": ["best3benchkg", "bench", "bestbench", "benchkg"],
    "deadlift": ["best3deadliftkg", "deadlift", "bestdeadlift", "deadliftkg"],
    "total": ["totalkg", "total"],
    "equipment": ["equipment"],
    "event": ["event"],
    "place": ["place"],
}


def norm(h):
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def find_header(headers, field):
    keys = CANON[field]
    for k in keys:
        for h in headers:
            if norm(h) == k:
                return h
    return None


def resolve_path(p):
    p = os.path.expanduser(str(p))
    if os.path.isabs(p):
        return os.path.normpath(p)
    base = os.environ.get("PWD") or os.getcwd()
    return os.path.normpath(os.path.join(base, p))


def sheet_ref(name):
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name) else "'" + name.replace("'", "''") + "'"
