from __future__ import annotations

from typing import cast

import pytest
from town_core.domain.config_models import CatalogBundle
from town_core.domain.enums import BehaviorId
from town_core.domain.m3_catalog_models import M3Catalogs
from town_core.society.m3_targeted_evidence import (
    AUTHORITY_PROBE_KEYS,
    BEHAVIOR_PROBE_KEYS,
    INVITATION_ACCEPTANCE_PROBE_KEY,
    AuthorityProbeKey,
    ProbeKey,
    execute_authority_probe,
    execute_behavior_probe,
    execute_invitation_acceptance_probe,
    generate_m3_targeted_evidence,
)


@pytest.mark.parametrize(
    ("behavior_id", "probe"),
    [
        pytest.param(behavior_id, probe, id=f"{behavior_id.value}-{probe}")
        for behavior_id in BehaviorId
        for probe in BEHAVIOR_PROBE_KEYS
    ],
)
def test_behavior_targeted_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    behavior_id: BehaviorId,
    probe: str,
) -> None:
    assertion_count = execute_behavior_probe(catalog, m3_catalogs, behavior_id, cast(ProbeKey, probe))

    assert assertion_count > 0


@pytest.mark.parametrize("probe", [pytest.param(probe, id=probe) for probe in AUTHORITY_PROBE_KEYS])
def test_authority_targeted_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
    probe: str,
) -> None:
    assertion_count, observation = execute_authority_probe(catalog, m3_catalogs, cast(AuthorityProbeKey, probe))

    assert assertion_count > 0
    assert observation


def test_sim_targeted_invitation_acceptance_probe(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    assertion_count, observation = execute_invitation_acceptance_probe(catalog, m3_catalogs)

    assert assertion_count > 0
    assert observation["invitation_accepted_event_count"] == 1
    assert observation["invitation_event_source_action_id"] == observation["invite_action_id"]
    assert observation["joint_source_invite_action_id"] == observation["invite_action_id"]
    assert observation["joint_authority"] == "CENTRAL_RESOLVER"
    assert observation["joint_terminal_phase"] == "COMPLETED"
    assert observation["reservation_remnant_count"] == 0
    assert observation["replay_match"] is True


def test_targeted_evidence_has_176_distinct_executable_behavior_records_and_real_authority_transactions(
    catalog: CatalogBundle,
    m3_catalogs: M3Catalogs,
) -> None:
    evidence = generate_m3_targeted_evidence(catalog, m3_catalogs)
    behavior_results = cast(dict[str, dict[str, dict[str, object]]], evidence["behavior_probe_results"])
    authority_results = cast(dict[str, dict[str, object]], evidence["authority_probe_results"])
    sim_authority_results = cast(dict[str, dict[str, object]], evidence["sim_authority_probe_results"])
    observations = cast(dict[str, dict[str, object]], evidence["authority_probe_observations"])
    records = [record for behavior in behavior_results.values() for record in behavior.values()]
    test_ids = [cast(list[str], record["test_ids"])[0] for record in records]

    assert list(behavior_results) == [item.value for item in BehaviorId]
    assert len(records) == 22 * 8
    assert len(set(test_ids)) == 22 * 8
    assert all(
        record == {"status": "PASS", "test_ids": record["test_ids"], "assertion_count": record["assertion_count"]}
        for record in records
    )
    assert all(cast(int, record["assertion_count"]) > 0 for record in records)
    assert set(authority_results) == set(AUTHORITY_PROBE_KEYS)
    assert set(sim_authority_results) == {INVITATION_ACCEPTANCE_PROBE_KEY}
    assert sim_authority_results[INVITATION_ACCEPTANCE_PROBE_KEY]["status"] == "PASS"
    assert cast(int, sim_authority_results[INVITATION_ACCEPTANCE_PROBE_KEY]["assertion_count"]) > 0
    authority_test_ids = [cast(list[str], record["test_ids"])[0] for record in authority_results.values()]
    assert len(set(authority_test_ids)) == len(AUTHORITY_PROBE_KEYS)
    assert all(
        record == {"status": "PASS", "test_ids": record["test_ids"], "assertion_count": record["assertion_count"]}
        and cast(int, record["assertion_count"]) > 0
        for record in authority_results.values()
    )
    assert (
        observations["knowledge_unknown_share_rejected"]["before_checkpoint_hash"]
        == observations["knowledge_unknown_share_rejected"]["after_checkpoint_hash"]
    )
    assert observations["joint_action_cancel_release"]["authority_transaction_count"] == 1
    assert observations["joint_action_failure_release"]["authority_transaction_count"] == 1
    assert cast(int, observations["joint_action_timeout_release"]["authority_transaction_count"]) > 1
    acceptance = observations[INVITATION_ACCEPTANCE_PROBE_KEY]
    assert cast(float, acceptance["deterministic_draw"]) <= cast(float, acceptance["acceptance_probability"])
    assert acceptance["invitation_accepted_event_count"] == 1
    assert acceptance["joint_created_phase_count"] == 1
    assert acceptance["joint_terminal_phase"] == "COMPLETED"
    assert acceptance["reservation_remnant_count"] == 0
    assert acceptance["replay_match"] is True
    assert all(
        observation["reservation_remnant_count"] == 0
        and observation["replay_match"] is True
        and observation["before_checkpoint_hash"] != observation["after_checkpoint_hash"]
        for name, observation in observations.items()
        if name.startswith("joint_action_")
    )
