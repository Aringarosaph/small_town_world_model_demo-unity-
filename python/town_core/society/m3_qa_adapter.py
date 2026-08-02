"""Generate SIM-owned M3 readiness evidence from production authority entry points."""

from __future__ import annotations

import argparse
import io
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from town_core.bridge.m3_runtime import M3BridgeRuntime
from town_core.catalogs import load_catalog, load_m3_catalogs
from town_core.cli import main as cli_main
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import M3_PROTOCOL_VERSION, BehaviorId, MessageType
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.domain.protocol_models import (
    AssetRegistryPayload,
    AssetRegistryV030Message,
    ClientHelloV030Message,
    ClientHelloV030Payload,
    ClientReadyPayload,
    ClientReadyV030Message,
    RegisteredInteractionSlot,
    RegisteredLocation,
    RegisteredNpcView,
    RegisteredObject,
    WorldSnapshotV030Message,
)
from town_core.simulation.clock import RuntimeMode
from town_core.society.checkpoint import load_checkpoint
from town_core.society.engine import SocietyEngine
from town_core.society.initialization import build_initial_society_checkpoint
from town_core.society.run import run_society

EVIDENCE_SCHEMA = "stwm.simulation.m3-readiness-evidence/v1"
PROJECT_NAME = "Small Town World Model（STWM）"
FIXED_7_DAY_SEEDS = (12345, 24680, 97531, 314159, 271828)
FIXED_30_DAY_SEEDS = (12345, 24680, 97531)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXED_SENT_AT_UTC = datetime(2026, 8, 3, tzinfo=UTC)


def _invoke_cli(arguments: Sequence[str]) -> tuple[int, dict[str, Any]]:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = cli_main(arguments)
    raw = output.getvalue().strip()
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise TypeError("M3 CLI output must be a JSON object")
    return exit_code, document


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("M3 readiness artifacts must remain below the external output root") from exc


def _ensure_external(output_root: Path, evidence_path: Path) -> None:
    repository = REPOSITORY_ROOT.resolve()
    output = output_root.resolve()
    evidence = evidence_path.resolve()
    if output == repository or repository in output.parents:
        raise ValueError("M3 readiness output_root must remain outside the repository")
    if evidence == repository or repository in evidence.parents:
        raise ValueError("M3 readiness evidence must remain outside the repository")
    if evidence.parent != output:
        raise ValueError("M3 readiness evidence must be a direct child of output_root")
    output_root.mkdir(parents=True, exist_ok=True)
    if evidence_path.exists():
        raise FileExistsError(f"M3 readiness evidence already exists: {evidence_path}")


def _run_document(name: str, summary: Mapping[str, Any], root: Path) -> dict[str, Any]:
    run_path = Path(str(summary["run_path"]))
    return {
        "name": name,
        "run_directory": _relative(run_path, root),
        "seed": int(summary["seed"]),
        "tick_count": int(summary["tick_count"]),
        "transaction_count": int(summary["transaction_count"]),
        "enabled_agent_ids": list(summary["enabled_agent_ids"]),
        "final_state_hash": str(summary["final_state_hash"]),
        "final_checkpoint_hash": str(summary["final_checkpoint_hash"]),
        "transaction_chain_hash": str(summary["transaction_chain_hash"]),
        "authority_log_hash": str(summary["authority_log_hash"]),
        "authority_record_count": int(summary["authority_record_count"]),
        "decision_count": int(summary["decision_count"]),
        "action_count": int(summary["action_count"]),
        "event_count": int(summary["event_count"]),
        "selected_behavior_counts": dict(summary["selected_behavior_counts"]),
        "event_type_counts": dict(summary["event_type_counts"]),
        "household_balances": dict(summary["household_balances"]),
        "knowledge_records": int(summary["knowledge_records"]),
        "conversation_records": int(summary["conversation_records"]),
        "pathology": dict(summary["pathology"]),
        "performance": dict(summary["performance"]),
        "invariants": dict(summary["invariants"]),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"expected object at {path.name}:{line_number}")
        records.append(value)
    return records


def _economy_evidence(catalog: CatalogBundle, run_path: Path) -> dict[str, Any]:
    initial = load_checkpoint(run_path / "initial_checkpoint.json")
    final = load_checkpoint(run_path / "final_checkpoint.json")
    action_records = _read_jsonl(run_path / "actions.jsonl")
    events = _read_jsonl(run_path / "events.jsonl")
    wage_by_household: Counter[str] = Counter()
    money_costs: Counter[str] = Counter()
    food_delta: Counter[str] = Counter()
    settlement_action_ids: set[str] = set()
    for envelope in events:
        payload = envelope["payload"]
        if payload["event_type"] != "WORK_COMPLETED":
            continue
        agent_id = str(payload["actor_ids"][0])
        household_id = final.world.agents[agent_id].household_id
        wage = payload["payload"]["wage_minor_units"]
        if not isinstance(wage, int):
            raise TypeError("M3 WORK_COMPLETED wage must be an integer")
        wage_by_household[household_id] += wage
    for envelope in action_records:
        payload = envelope["payload"]
        if payload["phase"] != "COMPLETED":
            continue
        action_id = str(payload["action_id"])
        if action_id in settlement_action_ids:
            raise ValueError("M3 completed action was recorded more than once")
        settlement_action_ids.add(action_id)
        behavior = BehaviorId(str(payload["behavior_id"]))
        agent_ids = [str(item) for item in payload["agent_ids"]]
        charged = agent_ids if bool(payload["joint"]) else agent_ids[:1]
        if behavior is BehaviorId.BUY_GROCERIES:
            household_id = final.world.agents[charged[0]].household_id
            money_costs[household_id] += catalog.economy.groceries.price
            food_delta[household_id] += catalog.economy.groceries.food_units_delta
        elif behavior is BehaviorId.EAT_AT_HOME:
            food_delta[final.world.agents[charged[0]].household_id] -= 1
        elif behavior in {BehaviorId.EAT_AT_CAFE, BehaviorId.DRINK_AT_BAR}:
            price = (
                catalog.economy.cafe_meal.price
                if behavior is BehaviorId.EAT_AT_CAFE
                else catalog.economy.bar_drink.price
            )
            for agent_id in charged:
                money_costs[final.world.agents[agent_id].household_id] += price
    households: list[dict[str, object]] = []
    for household_id in sorted(final.world.households):
        initial_household = initial.world.households[household_id]
        final_household = final.world.households[household_id]
        expected_money = initial_household.money + wage_by_household[household_id] - money_costs[household_id]
        expected_food = initial_household.food_units + food_delta[household_id]
        households.append(
            {
                "household_id": household_id,
                "initial_money": initial_household.money,
                "unique_wages": wage_by_household[household_id],
                "purchase_and_consumption_costs": money_costs[household_id],
                "expected_money": expected_money,
                "actual_money": final_household.money,
                "initial_food_units": initial_household.food_units,
                "purchase_and_consumption_food_delta": food_delta[household_id],
                "expected_food_units": expected_food,
                "actual_food_units": final_household.food_units,
                "equation_matches": expected_money == final_household.money
                and expected_food == final_household.food_units,
            }
        )
    return {
        "households": households,
        "all_equations_match": all(bool(item["equation_matches"]) for item in households),
        "settlement_keys_unique": len(final.settlement_keys) == len(set(final.settlement_keys)),
        "resources_nonnegative": all(
            household.money >= 0 and household.food_units >= 0 for household in final.world.households.values()
        ),
    }


def _registry_payload(catalog: CatalogBundle, m3_catalogs: M3Catalogs) -> AssetRegistryPayload:
    manifest = m3_catalogs.semantic_instances
    return AssetRegistryPayload(
        locations=[
            RegisteredLocation(location_id=item.location_id, location_type=item.location_type)
            for item in catalog.locations.locations
        ],
        objects=[
            RegisteredObject(
                object_id=item.object_id,
                object_type=item.object_type,
                location_id=item.location_id,
                capability_tags=item.capability_tags,
                enabled=True,
                interaction_slots=[
                    RegisteredInteractionSlot(
                        slot_index=slot,
                        supported_animation_semantics=item.supported_animation_semantics,
                    )
                    for slot in range(item.slot_count)
                ],
            )
            for item in manifest.objects
        ],
        npc_views=[RegisteredNpcView(agent_id=item) for item in manifest.npc_view_ids],
        mapped_animation_semantics=list(manifest.required_animation_semantics),
    )


def _envelope(runtime: M3BridgeRuntime, message_id: str) -> dict[str, object]:
    return {
        "protocol_version": M3_PROTOCOL_VERSION,
        "message_id": message_id,
        "sent_at_utc": FIXED_SENT_AT_UTC,
        "world_id": runtime.world_id,
        "state_version": runtime.engine.state.state_version,
        "correlation_id": None,
    }


def _handshake(runtime: M3BridgeRuntime, prefix: str) -> tuple[Any, WorldSnapshotV030Message]:
    session = runtime.open_session()
    hello = ClientHelloV030Message.model_validate(
        {
            **_envelope(runtime, f"msg_{prefix}1"),
            "message_type": MessageType.CLIENT_HELLO,
            "payload": ClientHelloV030Payload(
                client_name="unity",
                unity_editor_version="6000.4.2f1",
                supported_protocol_versions=[cast(Any, M3_PROTOCOL_VERSION)],
            ),
        }
    )
    session.receive_json(hello.model_dump(mode="json"))
    registry = AssetRegistryV030Message.model_validate(
        {
            **_envelope(runtime, f"msg_{prefix}2"),
            "message_type": MessageType.ASSET_REGISTRY,
            "payload": _registry_payload(runtime.catalog, runtime.m3_catalogs),
        }
    )
    outputs = session.receive_json(registry.model_dump(mode="json"))
    snapshot = outputs[1]
    if not isinstance(snapshot, WorldSnapshotV030Message):
        raise TypeError("M3 registry handshake did not emit a full snapshot")
    return session, snapshot


def _bridge_evidence(catalog: CatalogBundle, m3_catalogs: M3Catalogs, seed: int) -> dict[str, Any]:
    checkpoint = build_initial_society_checkpoint(catalog, m3_catalogs, seed=seed)
    engine = SocietyEngine(catalog, m3_catalogs, checkpoint, runtime_mode=RuntimeMode.UNITY_LIVE)
    runtime = M3BridgeRuntime(catalog, m3_catalogs, engine, now=lambda: FIXED_SENT_AT_UTC)
    session, snapshot = _handshake(runtime, "8100000")
    gated_before_ready = False
    try:
        runtime.advance_one_minute()
    except ValueError as exc:
        gated_before_ready = "client_ready" in str(exc)
    ready = ClientReadyV030Message.model_validate(
        {
            **_envelope(runtime, "msg_81000003"),
            "state_version": snapshot.state_version,
            "message_type": MessageType.CLIENT_READY,
            "payload": ClientReadyPayload(registry_message_id="msg_81000002"),
        }
    )
    session.receive_json(ready.model_dump(mode="json"))
    first_generation_messages = runtime.advance_one_minute()
    old_version = runtime.engine.state.state_version
    old_session = session
    new_session, fresh_snapshot = _handshake(runtime, "8200000")
    obsolete_rejected = False
    try:
        old_session.receive_json({})
    except ValueError as exc:
        obsolete_rejected = "OBSOLETE_CONNECTION_GENERATION" in str(exc)
    return {
        "semantic_profile": "M3_FULL",
        "catalog_protocol_version": catalog.world.protocol_version,
        "negotiated_protocol_version": M3_PROTOCOL_VERSION,
        "client_ready_gate_observed": gated_before_ready,
        "first_generation_ready": runtime.evidence()["sessions"][0]["ready_acknowledged"],
        "first_generation_message_counts": dict(
            sorted(Counter(item.message_type.value for item in first_generation_messages).items())
        ),
        "reconnect_generation": new_session.generation,
        "fresh_snapshot_state_version": fresh_snapshot.state_version,
        "fresh_snapshot_covers_all_active_actions": {
            item.action_id for item in fresh_snapshot.payload.active_presentations
        }
        == set(fresh_snapshot.payload.world.active_actions),
        "fresh_snapshot_not_older_than_prior_generation": fresh_snapshot.state_version >= old_version,
        "obsolete_generation_rejected": obsolete_rejected,
        "new_generation_ready_before_ack": runtime.ready,
        "sessions": runtime.evidence()["sessions"],
    }


def generate_evidence(
    *,
    config_path: Path,
    output_root: Path,
    evidence_path: Path,
    seed: int,
    days: int,
) -> dict[str, Any]:
    if days <= 0:
        raise ValueError("M3 readiness days must be positive")
    _ensure_external(output_root, evidence_path)
    catalog = load_catalog(config_path)
    m3_catalogs = load_m3_catalogs(config_path, catalog=catalog)
    matrix = (("baseline", 1), ("repeat", 1), ("chunk_7", 7), ("chunk_60", 60))
    summaries: dict[str, dict[str, Any]] = {}
    baseline_path = output_root / "baseline"
    baseline_exit, baseline = _invoke_cli(
        (
            "run-society",
            "--config",
            str(config_path),
            "--days",
            str(days),
            "--seed",
            str(seed),
            "--chunk-minutes",
            "1",
            "--out",
            str(baseline_path),
        )
    )
    if baseline_exit != 0:
        raise RuntimeError(f"M3 baseline CLI failed: {baseline}")
    summaries["baseline"] = baseline
    for name, chunk in matrix[1:]:
        summaries[name] = run_society(
            catalog,
            m3_catalogs,
            days=days,
            seed=seed,
            run_path=output_root / name,
            chunk_minutes=chunk,
        )

    replay_exit, replay = _invoke_cli(
        (
            "replay-society",
            "--run",
            str(baseline_path),
            "--output-root",
            str(output_root),
        )
    )
    if replay_exit != 0:
        raise RuntimeError(f"M3 replay CLI failed: {replay}")
    checkpoint_path = baseline_path / "checkpoints" / "checkpoint_00000360.json"
    resume_summary = run_society(
        catalog,
        m3_catalogs,
        days=days,
        seed=seed,
        run_path=output_root / "resume_360",
        chunk_minutes=60,
        resume_checkpoint=load_checkpoint(checkpoint_path),
    )
    invalid_exit, invalid_output = _invoke_cli(
        (
            "run-society",
            "--config",
            str(config_path),
            "--days",
            "0",
            "--out",
            str(output_root / "invalid_should_not_exist"),
        )
    )

    runs = [_run_document(name, summaries[name], output_root) for name, _ in matrix]
    hash_fields = (
        "final_state_hash",
        "final_checkpoint_hash",
        "transaction_chain_hash",
        "authority_log_hash",
    )
    determinism = {
        "compared_runs": [name for name, _ in matrix],
        "hash_fields": list(hash_fields),
        "all_hashes_match": all(len({str(summaries[name][field]) for name, _ in matrix}) == 1 for field in hash_fields),
    }
    resume_match = all(str(resume_summary[field]) == str(summaries["baseline"][field]) for field in hash_fields)
    bridge = _bridge_evidence(catalog, m3_catalogs, seed)
    economy = _economy_evidence(catalog, baseline_path)
    replay_document = {
        "output_directory": _relative(Path(str(replay["replay_output_path"])), output_root),
        "transaction_count": int(replay["transaction_count"]),
        "expected_final_checkpoint_hash": str(replay["expected_final_checkpoint_hash"]),
        "actual_final_checkpoint_hash": str(replay["actual_final_checkpoint_hash"]),
        "expected_authority_log_hash": str(replay["expected_authority_log_hash"]),
        "actual_authority_log_hash": str(replay["actual_authority_log_hash"]),
        "match": bool(replay["match"]),
    }
    evidence: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "project_name": PROJECT_NAME,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "scenario": {
            "seed": seed,
            "days": days,
            "semantic_profile": "M3_FULL",
            "enabled_agent_ids": [f"npc_{index:02d}" for index in range(1, 11)],
        },
        "protocol": {
            "catalog_protocol_version": catalog.world.protocol_version,
            "active_negotiated_protocol_version": M3_PROTOCOL_VERSION,
            "checkpoint_schema": "stwm.simulation.m3-authority-checkpoint/v1",
        },
        "runs": runs,
        "determinism": determinism,
        "replay": replay_document,
        "checkpoint_resume": {
            "source_checkpoint": _relative(checkpoint_path, output_root),
            "output_directory": _relative(Path(str(resume_summary["run_path"])), output_root),
            "resume_game_minute": 360,
            "hashes_match_baseline": resume_match,
        },
        "economy": economy,
        "bridge": bridge,
        "soak_plan": {
            "fixed_7_day_seeds": list(FIXED_7_DAY_SEEDS),
            "fixed_30_day_seeds": list(FIXED_30_DAY_SEEDS),
            "full_slow_soak_executed": False,
            "reason": "deferred to sequential ORCH/QA release scheduling",
        },
        "cli_contract": {
            "run_society_exit_code": baseline_exit,
            "replay_society_exit_code": replay_exit,
            "invalid_input_exit_code": invalid_exit,
            "invalid_input_machine_readable": invalid_output.get("completed") is False,
        },
    }
    evidence["passed"] = bool(
        determinism["all_hashes_match"]
        and replay_document["match"]
        and resume_match
        and economy["all_equations_match"]
        and economy["settlement_keys_unique"]
        and economy["resources_nonnegative"]
        and bridge["client_ready_gate_observed"]
        and bridge["fresh_snapshot_covers_all_active_actions"]
        and bridge["obsolete_generation_rejected"]
        and baseline_exit == 0
        and replay_exit == 0
        and invalid_exit != 0
    )
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Small Town World Model（STWM） M3 readiness evidence")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--days", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = generate_evidence(
            config_path=args.config,
            output_root=args.output_root,
            evidence_path=args.evidence,
            seed=args.seed,
            days=args.days,
        )
    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
        print(
            json.dumps(
                {"completed": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
