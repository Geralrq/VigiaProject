"""Idempotent demo seed. Run from /backend:  uv run python -m scripts.seed

Every row gets a deterministic UUID (uuid5) and is inserted with
ON CONFLICT DO NOTHING, so re-running never duplicates or overwrites data.
Zone polygons are simplified bounding areas around real protected/forest
regions (approximate, for demo purposes only).
"""

import math
import random
import uuid
from datetime import UTC, date, datetime, timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.models import (
    AnomalyModel,
    CarbonFactorModel,
    FireHotspotModel,
    IndexReadingModel,
    ZoneModel,
)
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.settings import get_settings

NAMESPACE = uuid.UUID("5c1f6c52-7a0e-4f0a-9d3e-2b8f0d0c7a11")
CO2_PER_C = 44 / 12  # tC -> tCO2e
DEMO_DAY = date(2026, 11, 15)  # anchor for the demo scenario
READING_STEP_DAYS = 10
READINGS_PER_INDEX = 13  # ~4 months, ending at DEMO_DAY


def uid(*parts: object) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts))


# tC/ha of reference carbon stock per cover type. Configurable: adjust via DB.
CARBON_FACTORS = {
    "bosque_humedo_tropical": 150.0,
    "bosque_amazonico": 180.0,
    "bosque_andino": 120.0,
    "paramo": 60.0,
    "pastizal": 10.0,
}

# (key, nombre, tipo_cobertura, (min_lon, min_lat, max_lon, max_lat), umbral_ndvi, umbral_nbr)
ZONES = [
    (
        "paramillo",
        "PNN Paramillo (sector Antioquia)",
        "bosque_humedo_tropical",
        (-76.20, 7.00, -75.90, 7.35),
        0.15,
        0.20,
    ),
    (
        "rio_claro",
        "Reserva Cañón del Río Claro (Puerto Triunfo)",
        "bosque_humedo_tropical",
        (-74.95, 5.85, -74.80, 5.97),
        0.15,
        0.20,
    ),
    (
        "guaviare",
        "Amazonía – frente de deforestación Calamar/Miraflores (Guaviare)",
        "bosque_amazonico",
        (-72.80, 1.85, -72.50, 2.10),
        0.15,
        0.20,
    ),
]

# Baseline mean per (zone, index) and the demo drop applied over the last readings.
BASELINE = {"NDVI": 0.82, "NBR": 0.62}
SCENARIOS = {
    # zone key: (index, final value, readings over which the drop happens)
    "paramillo": ("NBR", 0.08, 2),  # fire: sharp NBR collapse
    "guaviare": ("NDVI", 0.41, 4),  # deforestation: NDVI falls
}


def _ids(zone_key: str) -> uuid.UUID:
    return uid("zone", zone_key)


def seed_zones(session: Session) -> None:
    for key, nombre, cover, bounds, u_ndvi, u_nbr in ZONES:
        session.execute(
            insert(ZoneModel)
            .values(
                id=_ids(key),
                nombre=nombre,
                tipo_cobertura=cover,
                geom=from_shape(box(*bounds), srid=4326),
                umbral_ndvi=u_ndvi,
                umbral_nbr=u_nbr,
                activa=True,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )


def seed_carbon_factors(session: Session) -> None:
    for cover, tc in CARBON_FACTORS.items():
        session.execute(
            insert(CarbonFactorModel)
            .values(id=uid("carbon", cover), tipo_cobertura=cover, tc_por_ha=tc)
            .on_conflict_do_nothing(index_elements=["tipo_cobertura"])
        )


def seed_readings(session: Session) -> None:
    rng = random.Random(42)  # fixed seed -> reproducible noise
    for key, *_ in ZONES:
        for index, base in BASELINE.items():
            scenario = SCENARIOS.get(key)
            for i in range(READINGS_PER_INDEX):
                days_back = (READINGS_PER_INDEX - 1 - i) * READING_STEP_DAYS
                fecha = DEMO_DAY - timedelta(days=days_back)
                valor = base + rng.uniform(-0.02, 0.02)
                if scenario and scenario[0] == index:
                    _, final, span = scenario
                    steps_into_drop = i - (READINGS_PER_INDEX - span)
                    if steps_into_drop >= 0:
                        frac = (steps_into_drop + 1) / span
                        valor = base + (final - base) * frac + rng.uniform(-0.01, 0.01)
                nubosidad = round(rng.uniform(0, 35), 1)
                session.execute(
                    insert(IndexReadingModel)
                    .values(
                        id=uid("reading", key, index, fecha.isoformat()),
                        zone_id=_ids(key),
                        indice=index,
                        fecha=fecha,
                        valor=round(valor, 4),
                        nubosidad=nubosidad,
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )


def _ring(lon: float, lat: float, radius_deg: float, n: int = 12) -> list[tuple[float, float]]:
    return [
        (
            lon + radius_deg * math.cos(2 * math.pi * k / n),
            lat + radius_deg * math.sin(2 * math.pi * k / n),
        )
        for k in range(n)
    ]


def seed_demo_scenario(session: Session) -> None:
    from shapely.geometry import Polygon

    # 1) Fire in Paramillo: FIRMS-style VIIRS hotspots clustered around one point.
    fire_lon, fire_lat = -76.05, 7.18
    fire_when = datetime.combine(DEMO_DAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=18)
    offsets = [(0, 0), (0.004, 0.002), (-0.003, 0.004), (0.002, -0.005), (-0.005, -0.002)]
    for n, (dx, dy) in enumerate(offsets):
        session.execute(
            insert(FireHotspotModel)
            .values(
                id=uid("hotspot", "paramillo", n),
                geom=from_shape(Point(fire_lon + dx, fire_lat + dy), srid=4326),
                fecha=fire_when,
                confianza=90 - 5 * n,
                frp=round(22.5 - 3.1 * n, 1),
                fuente="VIIRS_SNPP_NRT",
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    fire_ha = 38.0
    session.execute(
        insert(AnomalyModel)
        .values(
            id=uid("anomaly", "paramillo-fire"),
            zone_id=_ids("paramillo"),
            tipo="INCENDIO",
            magnitud=round(0.62 - 0.08, 3),  # NBR drop
            confianza=0.91,
            hectareas=fire_ha,
            co2_estimado=round(fire_ha * CARBON_FACTORS["bosque_humedo_tropical"] * CO2_PER_C, 1),
            geom=from_shape(Polygon(_ring(fire_lon, fire_lat, 0.0045)), srid=4326),
            estado="DETECTADA",
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )

    # 2) Deforestation in Guaviare: NDVI loss over a cleared patch.
    defo_lon, defo_lat = -72.65, 1.98
    defo_ha = 120.0
    session.execute(
        insert(AnomalyModel)
        .values(
            id=uid("anomaly", "guaviare-deforestation"),
            zone_id=_ids("guaviare"),
            tipo="DEFORESTACION",
            magnitud=round(0.82 - 0.41, 3),
            confianza=0.87,
            hectareas=defo_ha,
            co2_estimado=round(defo_ha * CARBON_FACTORS["bosque_amazonico"] * CO2_PER_C, 1),
            geom=from_shape(
                box(defo_lon - 0.012, defo_lat - 0.009, defo_lon + 0.012, defo_lat + 0.009),
                srid=4326,
            ),
            estado="DETECTADA",
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )


# Fictitious volunteers so verification missions have recipients in the demo. They are
# CIUDADANO profiles flagged `es_demo`, placed near the demo scenario (Guaviare deforestation
# at -72.65,1.98 and Paramillo fire at -76.05,7.18). They are not auth users: nobody can log
# in as them. (key, nombre, (lon, lat))
DEMO_PROFILES = [
    ("guaviare-1", "Camila R. (demo)", (-72.66, 1.99)),  # ~1.5 km from the cleared patch
    ("guaviare-2", "Julián C. (demo)", (-72.60, 2.02)),  # ~6.5 km
    ("paramillo-1", "Marcela O. (demo)", (-76.04, 7.19)),  # ~1.5 km from the fire
    ("paramillo-2", "Andrés V. (demo)", (-76.10, 7.14)),  # ~7 km
]


def seed_demo_profiles(session: Session) -> None:
    for key, nombre, (lon, lat) in DEMO_PROFILES:
        session.execute(
            insert(ProfileModel)
            .values(
                id=uid("profile", key),
                nombre=nombre,
                rol="CIUDADANO",
                ubicacion=from_shape(Point(lon, lat), srid=4326),
                puntos=0,
                es_demo=True,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )


def main() -> None:
    engine = build_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session, session.begin():
        seed_zones(session)
        seed_carbon_factors(session)
        seed_readings(session)
        seed_demo_scenario(session)
        seed_demo_profiles(session)
    print("Seed applied (idempotent).")


if __name__ == "__main__":
    main()
