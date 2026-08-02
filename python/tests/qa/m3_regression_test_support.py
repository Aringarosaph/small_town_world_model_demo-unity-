from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.diagnostics import check_m1, check_m2
from tools.diagnostics.run_m3_regressions import ProcessResult


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FakeRegressionRunner:
    def __init__(
        self,
        *,
        fail_step: str | None = None,
        pending_step: str | None = None,
        skipped_step: str | None = None,
    ) -> None:
        self.fail_step = fail_step
        self.pending_step = pending_step
        self.skipped_step = skipped_step
        self.observed_steps: list[str] = []

    @staticmethod
    def _step_id(argv: Sequence[str]) -> str:
        joined = " ".join(argv)
        if "check_m0.py" in joined:
            return "m0_diagnostics"
        if "check_m1.py" in joined:
            return "m1_diagnostics"
        if "check_m2.py" in joined:
            return "m2_diagnostics"
        marker = argv[argv.index("-m", 3) + 1]
        return f"{marker}_tests"

    def __call__(
        self,
        argv: Sequence[str],
        cwd: Path,
        environment: Mapping[str, str],
        timeout: int,
    ) -> ProcessResult:
        del environment, timeout
        step_id = self._step_id(argv)
        self.observed_steps.append(step_id)
        if step_id == self.fail_step:
            return ProcessResult(7, "", f"forced failure at {cwd}; password=not-a-real-secret")
        if step_id.endswith("_diagnostics"):
            report_path = Path(argv[argv.index("--json-output") + 1])
            schema = {
                "m0_diagnostics": "aitown.qa.m0-diagnostics/v1",
                "m1_diagnostics": check_m1.REPORT_SCHEMA,
                "m2_diagnostics": check_m2.REPORT_SCHEMA,
            }[step_id]
            pending = 1 if step_id == self.pending_step else 0
            write_json(
                report_path,
                {
                    "schema": schema,
                    "project_name": "Small Town World Model（STWM）",
                    "repository_root": str(cwd),
                    "findings": [],
                    "summary": {"pass": 1, "pending": pending, "fail": 0},
                },
            )
            if step_id == "m1_diagnostics":
                m1_root = Path(argv[argv.index("--output-root") + 1])
                write_json(
                    m1_root / "m1_qa_evidence.json",
                    {
                        "schema": check_m1.EVIDENCE_SCHEMA,
                        "project_name": "Small Town World Model（STWM）",
                    },
                )
        else:
            junit_path = Path(argv[argv.index("--junitxml") + 1])
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            skipped = 1 if step_id == self.skipped_step else 0
            junit_path.write_text(
                '<testsuites><testsuite name="/Users/tester/repository" tests="1" failures="0" errors="0" '
                f'skipped="{skipped}" /></testsuites>\n',
                encoding="utf-8",
            )
        return ProcessResult(
            0,
            f"completed {step_id} under {cwd}",
            "authorization=not-a-real-secret-token",
        )
