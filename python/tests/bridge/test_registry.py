from __future__ import annotations

from town_core.bridge.registry import M2ScopedAssetRegistryValidator
from town_core.bridge.runtime import BridgeRuntime
from town_core.domain.enums import AssetValidationSeverity

from .conftest import valid_registry_payload


def test_m2_scoped_registry_accepts_route_and_reports_full_v0_warnings(runtime: BridgeRuntime) -> None:
    result = M2ScopedAssetRegistryValidator(runtime.catalog, runtime.engine.state).validate(
        valid_registry_payload(runtime)
    )

    assert result.accepted
    assert not [issue for issue in result.issues if issue.severity is AssetValidationSeverity.ERROR]
    assert any(issue.code == "V0_LOCATION_NOT_REGISTERED" for issue in result.issues)
    assert any(issue.code == "V0_NPC_VIEW_NOT_REGISTERED" for issue in result.issues)
    assert result.issues == sorted(
        result.issues,
        key=lambda item: (
            {"ERROR": 0, "WARNING": 1, "INFO": 2}[item.severity.value],
            item.code,
            item.entity_id or "",
            item.message,
        ),
    )


def test_duplicate_or_missing_required_semantics_block_registry(runtime: BridgeRuntime) -> None:
    payload = valid_registry_payload(runtime)
    payload = payload.model_copy(
        update={
            "locations": [*payload.locations, payload.locations[0]],
            "objects": [obj for obj in payload.objects if obj.object_id != "home_a_bed_01"],
        }
    )

    result = M2ScopedAssetRegistryValidator(runtime.catalog, runtime.engine.state).validate(payload)

    assert not result.accepted
    codes = {(issue.code, issue.entity_id) for issue in result.issues}
    assert ("DUPLICATE_LOCATION_ID", "home_a") in codes
    assert ("M2_OBJECT_MISSING", "home_a_bed_01") in codes
