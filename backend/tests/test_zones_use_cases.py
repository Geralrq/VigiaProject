from typing import Any

import pytest

from app.monitoring.adapters.outbound.persistence.zone_repository import to_domain, to_row
from app.monitoring.application.use_cases.create_zone import CreateZone, CreateZoneCommand
from app.monitoring.application.use_cases.list_zones import ListZones
from app.monitoring.domain.zone import Zone
from app.shared.domain.errors import DomainValidationError
from tests.fakes import InMemoryZoneRepository


def square(lon: float = -75.5, lat: float = 6.2, d: float = 0.1) -> dict[str, Any]:
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def command(**overrides: Any) -> CreateZoneCommand:
    data: dict[str, Any] = {
        "name": "  Reserva Río Claro ",
        "cover_type": "bosque_humedo_tropical",
        "geometry": square(),
        "ndvi_threshold": 0.15,
        "nbr_threshold": 0.2,
    }
    return CreateZoneCommand(**(data | overrides))


def test_create_zone_persists_through_port() -> None:
    repo = InMemoryZoneRepository()
    zone = CreateZone(repo).execute(command())
    assert repo.zones == [zone]
    assert zone.name == "Reserva Río Claro"
    assert zone.active is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "   "},
        {"ndvi_threshold": 1.5},
        {"geometry": {"type": "Point", "coordinates": [-75.5, 6.2]}},
        {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}},
        {"geometry": square(lon=200)},
    ],
    ids=["blank-name", "threshold-range", "not-polygon", "open-ring", "lon-out-of-range"],
)
def test_create_zone_rejects_invalid_input(overrides: dict[str, Any]) -> None:
    repo = InMemoryZoneRepository()
    with pytest.raises(DomainValidationError):
        CreateZone(repo).execute(command(**overrides))
    assert repo.zones == []


def test_list_zones_filters_active() -> None:
    active = Zone("B activa", "paramo", square(), 0.1, 0.1)
    inactive = Zone("A inactiva", "paramo", square(), 0.1, 0.1, active=False)
    use_case = ListZones(InMemoryZoneRepository([active, inactive]))
    assert use_case.execute() == [inactive, active]  # sorted by name
    assert use_case.execute(only_active=True) == [active]


def test_sqlalchemy_mapping_round_trip() -> None:
    zone = Zone("Paramillo", "bosque_humedo_tropical", square(), 0.15, 0.2)
    row = to_row(zone)
    assert (row.nombre, row.tipo_cobertura, row.umbral_ndvi) == ("Paramillo", zone.cover_type, 0.15)
    assert to_domain(row) == zone
