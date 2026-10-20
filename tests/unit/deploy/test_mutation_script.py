"""Tests for the verdict of ``scripts/mutation.sh``: its exit code is the judge's, and nothing else.

The script decides nothing about the score in its DIR modes: ``beadloom mutation --stats
... --min-score`` judges, and the script must exit with that verdict. Nothing short of a
run holds it to that - a script that printed "the score is under it" and exited 0 passed
review once. So the script runs here end to end, in a skeleton of the repository under
``tmp_path`` with the real adapter; the stand-ins on PATH are ``uv`` (which hands
``python`` to this interpreter and ``mutmut`` to a stand-in), mutmut itself, whose
verdicts a test sets, and - except where the real one is asked - beadloom's judge.

The stand-in judge scores ``killed / (killed + survived)`` against the floor it is given,
as a fraction. beadloom judges a sample by its interval rather than its point score, so
the samples here sit where the two agree (50 % clearly under, 85 % at the floor), and the
same two samples are put to beadloom itself where it is installed - it is not in the
suite's environment on CI, and the skip says so.
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.workflows import ROOT

SCRIPT = ROOT / "scripts" / "mutation.sh"
ADAPTER = ROOT / ".github" / "scripts" / "mutmut_adapter.py"
FLOW = ROOT / ".beadloom" / "flow.yml"
SOURCE = "src/horizon_tracker/domain/schedule.py"
MODULE = "horizon_tracker.domain.schedule"
FLOOR_PERCENT = "85"
BASH = shutil.which("bash")
JQ = shutil.which("jq")
REAL_BEADLOOM = shutil.which("beadloom")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash absent")

UV = f"""#!{sys.executable}
import os, sys
assert sys.argv[1] == "run", sys.argv
tool, rest = sys.argv[2], sys.argv[3:]
if tool == "python":
    os.execv(sys.executable, [sys.executable, *rest])
if tool == "mutmut":
    os.execv(sys.executable, [sys.executable, os.environ["STUB_MUTMUT"], *rest])
sys.exit(f"uv stand-in: no {{tool}}")
"""

MUTMUT = f"""import json, os, sys
from pathlib import Path
killed, survived = int(os.environ["STUB_KILLED"]), int(os.environ["STUB_SURVIVED"])
names = [f"{MODULE}.x_draw__mutmut_{{i}}" for i in range(1, killed + survived + 1)]
command, rest = sys.argv[1], sys.argv[2:]
if command == "export-cicd-stats":
    stats = {{"killed": killed, "survived": survived, "total": killed + survived,
              "no_tests": 0, "skipped": 0, "suspicious": 0, "timeout": 0, "not_checked": 0}}
    Path("mutants/mutmut-cicd-stats.json").write_text(json.dumps(stats))
    sys.exit(0)
assert command == "run", sys.argv
meta = Path("mutants/{SOURCE}.meta")
meta.parent.mkdir(parents=True, exist_ok=True)
codes = {{name: 1 if i < killed else 0 for i, name in enumerate(names)}}
meta.write_text(json.dumps({{"exit_code_by_key": codes}}))
if rest == ["horizon_tracker.no_such_function__mutmut_0"]:
    print("Filtered for specific mutants, but nothing matches")
    sys.exit(1)
"""

BEADLOOM = f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
assert args[0] == "mutation", args
def value(flag):
    return args[args.index(flag) + 1]
if "--stats" in args:
    stats = json.loads(Path(value("--stats")).read_text())
    floor = float(value("--min-score"))
    score = stats["killed"] / (stats["killed"] + stats["survived"])
    print(f"Score: {{score:.1%}}")
    if score < floor:
        print(f"Floor: {{floor:g}} - the score is under it")
        sys.exit(1)
    print(f"Floor: {{floor:g}} - held")
    sys.exit(0)
if "--json" in args:
    function = {{"path": "{SOURCE}", "name": "draw", "node": "schedule"}}
    print(json.dumps({{"change": {{"empty": False, "functions": [function]}}}}))
else:
    print("Population: 1 changed function")
"""


def executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


@dataclass(frozen=True)
class Run:
    """One run of the script: its exit code, what it printed and what it left in DIR."""

    returncode: int
    output: str
    out: Path
    judge_calls: list[list[str]]

    @property
    def outcome(self) -> str:
        path = self.out / "outcome"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def skeleton(tmp_path: Path) -> Path:
    """The repository as the script sees it: itself, the adapter, the flow, src/, tests/."""
    root = tmp_path / "repo"
    for source, target in [
        (SCRIPT, "scripts/mutation.sh"),
        (ADAPTER, ".github/scripts/mutmut_adapter.py"),
        (FLOW, ".beadloom/flow.yml"),
    ]:
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, root / target)
    domain = root / "src" / "horizon_tracker" / "domain"
    domain.mkdir(parents=True)
    (domain / "schedule.py").write_text("def draw():\n    return 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    return root


def run_script(
    tmp_path: Path, *args: str, killed: int, survived: int, real_judge: bool = False
) -> Run:
    root = skeleton(tmp_path)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    executable(stubs / "uv", UV)
    (tmp_path / "mutmut_stub.py").write_text(MUTMUT, encoding="utf-8")
    if real_judge:
        assert REAL_BEADLOOM is not None
        subprocess.run(
            [REAL_BEADLOOM, "reindex"], cwd=root, check=True, capture_output=True, text=True
        )
    else:
        executable(stubs / "beadloom", BEADLOOM)
    log = tmp_path / "beadloom.log"
    log.touch()
    out = tmp_path / "out"
    assert BASH is not None
    result = subprocess.run(
        [BASH, str(root / "scripts" / "mutation.sh"), *args, "--min-score", FLOOR_PERCENT],
        cwd=root,
        env={
            "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "STUB_MUTMUT": str(tmp_path / "mutmut_stub.py"),
            "STUB_KILLED": str(killed),
            "STUB_SURVIVED": str(survived),
            "STUB_LOG": str(log),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    judged = [call for call in calls if "--stats" in call]
    return Run(result.returncode, result.stdout + result.stderr, out, judged)


def per_change(tmp_path: Path, killed: int, survived: int) -> Run:
    return run_script(
        tmp_path,
        "--changed-since",
        "origin/main",
        "--out",
        str(tmp_path / "out"),
        killed=killed,
        survived=survived,
    )


def sampled(tmp_path: Path, killed: int, survived: int, *, real_judge: bool = False) -> Run:
    return run_script(
        tmp_path,
        "--sample",
        "100",
        "--seed",
        "2026-W43",
        "--out",
        str(tmp_path / "out"),
        killed=killed,
        survived=survived,
        real_judge=real_judge,
    )


# --- per change: the counters straddle the floor by one mutant ------------------------------


@pytest.mark.skipif(JQ is None, reason="jq absent: the per-change mode reads the plan with it")
def test_a_change_scored_under_the_floor_fails_the_script(tmp_path: Path) -> None:
    run = per_change(tmp_path, killed=84, survived=16)
    assert run.returncode == 1, run.output
    assert "the score is under it" in run.output
    # Red, and still a verdict: the summary reads the outcome, the exit code fails the job.
    assert run.outcome == "scored"


@pytest.mark.skipif(JQ is None, reason="jq absent: the per-change mode reads the plan with it")
def test_a_change_scored_at_the_floor_passes_the_script(tmp_path: Path) -> None:
    run = per_change(tmp_path, killed=85, survived=15)
    assert run.returncode == 0, run.output
    assert run.outcome == "scored"


@pytest.mark.skipif(JQ is None, reason="jq absent: the per-change mode reads the plan with it")
def test_the_judge_gets_the_floor_as_a_fraction_and_the_change(tmp_path: Path) -> None:
    run = per_change(tmp_path, killed=85, survived=15)
    (call,) = run.judge_calls
    assert call[call.index("--min-score") + 1] == "0.85"
    assert call[call.index("--changed-since") + 1] == "origin/main"


# --- the weekly sample ----------------------------------------------------------------------


def test_a_sample_scored_under_the_floor_fails_the_script(tmp_path: Path) -> None:
    run = sampled(tmp_path, killed=50, survived=50)
    assert run.returncode == 1, run.output
    assert run.outcome == "scored"


def test_a_sample_scored_at_the_floor_passes_the_script(tmp_path: Path) -> None:
    run = sampled(tmp_path, killed=85, survived=15)
    assert run.returncode == 0, run.output
    (call,) = run.judge_calls
    assert call[call.index("--min-score") + 1] == "0.85"
    assert call[call.index("--sample-of") + 1] == "100"


# --- the same two samples before beadloom's own judge ---------------------------------------


@pytest.mark.skipif(REAL_BEADLOOM is None, reason="beadloom is not installed in this environment")
@pytest.mark.parametrize(("killed", "survived", "verdict"), [(50, 50, 1), (85, 15, 0)])
def test_beadloom_judges_the_samples_as_the_stand_in_does(
    tmp_path: Path, killed: int, survived: int, verdict: int
) -> None:
    run = sampled(tmp_path, killed, survived, real_judge=True)
    assert run.returncode == verdict, run.output
    assert "Floor: 0.85" in run.output
    assert run.outcome == "scored"


# --- the full domain, judged by the script itself ----------------------------------------


def full(tmp_path: Path, killed: int, survived: int) -> Run:
    return run_script(tmp_path, killed=killed, survived=survived)


def test_the_full_domain_under_the_floor_fails_the_script(tmp_path: Path) -> None:
    run = full(tmp_path, killed=84, survived=16)
    assert run.returncode == 1, run.output
    assert "below 85%" in run.output


def test_the_full_domain_at_the_floor_passes_the_script(tmp_path: Path) -> None:
    run = full(tmp_path, killed=85, survived=15)
    assert run.returncode == 0, run.output
    assert "mutation score: 85.0%" in run.output
