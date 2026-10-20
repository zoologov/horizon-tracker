"""Turns a mutation plan into mutmut's exact mutant names, and counts exactly those names.

The glue between ``beadloom mutation`` and mutmut 3.8 that ``scripts/mutation.sh`` runs
for the per-change and the sampled modes of ``.github/workflows/mutation.yml``; a
simplified port of beadloom's own ``.github/scripts/mutmut_adapter.py``. beadloom answers
which functions a change touched and judges the score; mutmut runs the mutants; this file
is where the two meet:

``select``
    The exact names of the plan's functions' mutants, read from ``mutants/*.meta``.
    Exact names, not a glob per function: a glob ending ``__mutmut_*`` makes mutmut's
    clean run fall back to the whole selection (beadloom BDL-073).
``sample``
    A seeded random sample of exact names from the whole declared scope, and the size
    of the population it was drawn from (what ``--sample-of`` is given).
``count``
    The counters over exactly the selected names, in mutmut's own classification, and
    the survivors as ``{path, mutant}``. A selected name that never got a verdict makes
    the run silent, and is refused: every step exited 0 and the score would cover only
    the mutants the runner happened to reach.
``targets``
    The declared scope, ``mutation.targets`` of ``.beadloom/flow.yml``, one per line.

Run from the repository root: mutmut works in ``./mutants``. Every mutmut shape read
here is named where it is read; ``tests/unit/deploy/test_mutation_workflow.py`` holds
this file to them on a fabricated tree, and a run of the script holds it to mutmut.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

#: Where mutmut writes its mutated copy, with one ``<source>.meta`` per source file.
MUTANTS = Path("mutants")
META_SUFFIX = ".meta"

#: A mutant name ends ``__mutmut_<N>``.
MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")

#: A method's mangled name is ``xǁ<Class>ǁ<method>``; a function's is ``x_<function>``.
CLASS_SEPARATOR = "ǁ"
FUNCTION_PREFIX = "x_"

#: The counters written: mutmut's ``export-cicd-stats`` names, underscores for spaces.
COUNTER_NAMES = (
    "killed",
    "survived",
    "no_tests",
    "skipped",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
    "caught_by_type_check",
    "not_checked",
)

FLOW = Path(".beadloom") / "flow.yml"


class ShapeError(RuntimeError):
    """mutmut or beadloom wrote something in a shape this adapter was not written for."""


def function_of(name: str) -> str:
    """The function a mutant belongs to: ``function`` or ``Class.method``."""
    mangled = MUTANT_SUFFIX.sub("", name)
    if mangled == name:
        raise ShapeError(f"{name!r} does not end in __mutmut_<N>")
    local = mangled.rpartition(".")[2]
    if local.startswith(f"x{CLASS_SEPARATOR}"):
        parts = local.split(CLASS_SEPARATOR)
        if len(parts) == 3 and all(parts[1:]):
            return f"{parts[1]}.{parts[2]}"
    elif local.startswith(FUNCTION_PREFIX) and len(local) > len(FUNCTION_PREFIX):
        return local[len(FUNCTION_PREFIX) :]
    raise ShapeError(f"{name!r} is in no mutant-name shape mutmut 3.8 writes")


def read_metas() -> dict[str, dict[str, int | None]]:
    """Every ``.meta`` under ``mutants/``: source path -> exit code by mutant name."""
    metas: dict[str, dict[str, int | None]] = {}
    for path in sorted(MUTANTS.rglob(f"*.py{META_SUFFIX}")):
        source = path.relative_to(MUTANTS).as_posix().removesuffix(META_SUFFIX)
        data = json.loads(path.read_text(encoding="utf-8"))
        codes = data.get("exit_code_by_key") if isinstance(data, dict) else None
        if not isinstance(codes, dict):
            raise ShapeError(f"{path} holds no exit_code_by_key object")
        metas[source] = {str(name): code for name, code in codes.items()}
    if not metas:
        raise ShapeError(f"no {META_SUFFIX} file under {MUTANTS}/: the mutants were not generated")
    return metas


def write_names(path: str, names: list[str]) -> None:
    Path(path).write_text("".join(f"{name}\n" for name in names), encoding="utf-8")


def read_names(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def select(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    functions = plan.get("change", {}).get("functions")
    if not isinstance(functions, list):
        raise ShapeError(f"{args.plan}: no change.functions list - not a --changed-since plan")
    metas = read_metas()
    names: list[str] = []
    for function in functions:
        path, wanted = str(function["path"]), str(function["name"])
        own = [name for name in metas.get(path, {}) if function_of(name) == wanted]
        print(f"  {path} {wanted}: {len(own)} mutant(s)")
        names.extend(own)
    names = list(dict.fromkeys(names))
    write_names(args.names_out, names)
    print(f"Selected {len(names)} mutant(s) of {len(functions)} changed function(s)")
    return 0


def sample(args: argparse.Namespace) -> int:
    everything = sorted(name for names in read_metas().values() for name in names)
    size = min(args.size, len(everything))
    # A sample, not a secret: the seed makes a week's draw reproducible from the commit.
    drawn = sorted(random.Random(args.seed).sample(everything, size))
    write_names(args.names_out, drawn)
    Path(args.population_out).write_text(f"{len(everything)}\n", encoding="utf-8")
    print(f"Sampled {size} of {len(everything)} mutant(s) of the declared scope, seed {args.seed}")
    return 0


def status_table() -> dict[int | None, str]:
    """mutmut's own exit-code classification (``mutmut.stats`` in 3.8)."""
    from mutmut.stats import status_by_exit_code  # only `count` needs mutmut

    return status_by_exit_code


def count(args: argparse.Namespace) -> int:
    names = read_names(args.names)
    if not names:
        raise ShapeError(f"{args.names} names no mutant: there is nothing to count")
    metas = read_metas()
    source_of = {name: source for source, codes in metas.items() for name in codes}
    table = status_table()
    counters = dict.fromkeys(COUNTER_NAMES, 0)
    survivors: list[dict[str, str]] = []
    for name in names:
        if name not in source_of:
            raise ShapeError(f"{name} is in no {META_SUFFIX} file under {MUTANTS}/")
        code = metas[source_of[name]][name]
        status = table.get(code, "suspicious").replace(" ", "_")
        counters[status] = counters.get(status, 0) + 1
        if status == "survived":
            survivors.append({"path": source_of[name], "mutant": name})
    Path(args.stats_out).write_text(json.dumps(counters, indent=2) + "\n", encoding="utf-8")
    Path(args.survivors_out).write_text(json.dumps(survivors, indent=2) + "\n", encoding="utf-8")
    print(", ".join(f"{key} {value}" for key, value in counters.items() if value))
    if counters["not_checked"]:
        sys.exit(
            f"mutation: {counters['not_checked']} of {len(names)} selected mutant(s) were never"
            " checked - the run is silent and its score would be a guess"
        )
    return 0


def targets(_: argparse.Namespace) -> int:
    import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs

    flow = yaml.safe_load(FLOW.read_text(encoding="utf-8"))
    declared = flow.get("mutation", {}).get("targets") if isinstance(flow, dict) else None
    if not isinstance(declared, list) or not declared:
        raise ShapeError(f"{FLOW} declares no mutation.targets")
    for target in declared:
        print(target)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    commands = parser.add_subparsers(dest="command", required=True)

    chosen = commands.add_parser("select", help="exact names of a change's mutants")
    chosen.add_argument("--plan", required=True)
    chosen.add_argument("--names-out", required=True)
    chosen.set_defaults(handler=select)

    drawn = commands.add_parser("sample", help="a seeded random sample of the scope")
    drawn.add_argument("--size", type=int, required=True)
    drawn.add_argument("--seed", required=True)
    drawn.add_argument("--names-out", required=True)
    drawn.add_argument("--population-out", required=True)
    drawn.set_defaults(handler=sample)

    counted = commands.add_parser("count", help="counters over exactly the names run")
    counted.add_argument("--names", required=True)
    counted.add_argument("--stats-out", required=True)
    counted.add_argument("--survivors-out", required=True)
    counted.set_defaults(handler=count)

    declared = commands.add_parser("targets", help="the declared scope, one per line")
    declared.set_defaults(handler=targets)

    args = parser.parse_args(argv)
    try:
        result: int = args.handler(args)
    except ShapeError as error:
        sys.exit(f"mutmut_adapter: {error}")
    return result


if __name__ == "__main__":
    sys.exit(main())
