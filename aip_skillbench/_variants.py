"""The compile variants: one recipe each of authoring skill, toolchain, gate, and pack dir.

A variant is what `bootstrap --variant`, `convert --variant`, `eval --variant`, and a
campaign scenario name. Three exist (docs/aip-version-ablation-benchmark.md):

    aip-0.6a1   the aip-spec authoring skill at v0.6a1 plus aip v0.6a1 (client, server,
                wheels, runtime skill); gate `aip-spec validate`, strict on
                runtime_block_outdated. The only variant with a runtime, so the only one
                `eval --mode aip-runtime` accepts.
    aip-0.3a3   the aip repo at tag v0.3a3, which was the authoring skill itself (SKILL.md,
                assets/, references/, scripts/validate.py); gate that validator. No
                runtime: packs are mounted as skills only.
    dist        the distillation meta-skill in this repo (distillation/): components and
                scripts, no graph, no AIP; gate `dist_gate` below.

Everything per variant lives under build/<name>/ (gitignored, rebuilt by bootstrap) and
generated-skills/<task>/<name>/ (committed packs). bootstrap writes build/<name>/REF.json
and merges it into generated-skills/REFS.json, which is committed with the packs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATED_SKILLS = ROOT / "generated-skills"
REFS_FILE = GENERATED_SKILLS / "REFS.json"

AIP_REMOTE = "git@github.com:zach-blumenfeld/aip.git"
AIP_SPEC_REMOTE = "git@github.com:zach-blumenfeld/aip-spec.git"


@dataclass(frozen=True)
class Variant:
    name: str
    kind: str  # "aip" | "aip-legacy" | "dist"
    skill_name: str  # the authoring skill's folder name inside the workspace's .claude/skills/
    aip_ref: str | None = None
    aip_spec_ref: str | None = None
    skill_source: Path | None = None  # dist: the in-repo skill folder

    # --- build/<name>/ ---
    @property
    def build_dir(self) -> Path:
        return ROOT / "build" / self.name

    def src_dir(self, repo: str) -> Path:
        """Clone of `aip` or `aip-spec` for this variant."""
        return self.build_dir / "src" / repo

    @property
    def skill_dir(self) -> Path:
        """Holds <skill_name>/, copied into every authoring workspace."""
        return self.build_dir / "skill"

    @property
    def authoring_skill(self) -> Path:
        return self.skill_dir / self.skill_name

    @property
    def wheels_dir(self) -> Path:
        return self.build_dir / "wheels"

    @property
    def runtime_skill_dir(self) -> Path:
        """Skills dir holding only aip-runtime/SKILL.md, mounted in aip-runtime trials."""
        return self.build_dir / "aip-runtime-skill"

    @property
    def ref_file(self) -> Path:
        return self.build_dir / "REF.json"

    @property
    def has_runtime(self) -> bool:
        return self.kind == "aip"

    @property
    def is_aip(self) -> bool:
        """Packs carry an AIP procedure (either generation); the report reads AIP signals."""
        return self.kind in ("aip", "aip-legacy")

    # --- generated-skills/<task>/ ---
    def pack_root(self, task: str) -> Path:
        return GENERATED_SKILLS / task / self.name

    def record_dir(self, task: str) -> Path:
        return GENERATED_SKILLS / task / "_authoring" / self.name

    def read_ref(self) -> dict:
        if not self.ref_file.exists():
            return {}
        return json.loads(self.ref_file.read_text())


VARIANTS: dict[str, Variant] = {
    v.name: v
    for v in (
        Variant("aip-0.6a1", "aip", "aip", aip_ref="v0.6a1", aip_spec_ref="v0.6a1"),
        Variant("aip-0.3a3", "aip-legacy", "aip", aip_ref="v0.3a3"),
        Variant("dist", "dist", "skill-distillation", skill_source=ROOT / "distillation"),
    )
}
RUNTIME_VARIANTS = [v.name for v in VARIANTS.values() if v.has_runtime]


def variant(name: str) -> Variant:
    try:
        return VARIANTS[name]
    except KeyError:
        raise ValueError(f"unknown variant {name!r}; one of {', '.join(VARIANTS)}") from None


def read_refs() -> dict:
    """generated-skills/REFS.json: {variant name: its REF.json block}."""
    if not REFS_FILE.exists():
        return {}
    return json.loads(REFS_FILE.read_text())


# ---------------------------------------------------------------- the dist gate

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FENCE = re.compile(r"^```(\w*)[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
# Relative paths the body mentions: scripts/x.py, references/y.md, assets/z, source/...
_REL_PATH = re.compile(r"(?<![\w/.-])((?:scripts|references|assets|source)/[\w./-]+)")


def dist_gate(skill_dir: Path) -> list[str]:
    """Problems with a dist pack; empty means it passes.

    Agent Skills frontmatter (`name`, `description`), `name` equals the folder and is
    kebab-case under 65 chars, `source/` exists, every relative path the body mentions
    resolves inside the pack, and the pack is not an AIP pack in disguise: no AIP runtime
    block heading and no fenced YAML block that parses to a mapping with a `steps` key.
    """
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_dir}: no SKILL.md"]
    text = skill_md.read_text()
    m = _FRONTMATTER.match(text)
    if not m:
        return [f"{skill_md}: no YAML frontmatter"]
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as err:
        return [f"{skill_md}: frontmatter is not YAML: {err}"]
    body = m.group(2)
    name = fm.get("name")
    if not isinstance(name, str) or not name:
        problems.append("frontmatter: missing `name`")
    else:
        if name != skill_dir.name:
            problems.append(f"frontmatter: name {name!r} != folder {skill_dir.name!r}")
        if not _NAME.match(name) or len(name) >= 65:
            problems.append(f"frontmatter: name {name!r} is not kebab-case under 65 chars")
    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        problems.append("frontmatter: missing `description`")
    if not (skill_dir / "source").is_dir():
        problems.append("no source/ folder")
    for rel in sorted(set(_REL_PATH.findall(body))):
        if not (skill_dir / rel.rstrip(".,:)")).exists():
            problems.append(f"body mentions {rel} but it does not exist in the pack")
    if re.search(r"^#+\s*AIP runtime", body, re.MULTILINE | re.IGNORECASE):
        problems.append("body has an AIP runtime block: this is an AIP pack, not a dist pack")
    if "aip-version" in m.group(1):
        problems.append("frontmatter declares metadata.aip-version: this is an AIP pack, not a dist pack")
    for lang, block in _FENCE.findall(body):
        if lang.lower() not in ("yaml", "yml", ""):
            continue
        try:
            doc = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict) and "steps" in doc:
            problems.append("body has a fenced YAML procedure with `steps`: this is an AIP pack, not a dist pack")
            break
    return [f"{skill_md}: {p}" for p in problems]
