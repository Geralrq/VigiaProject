import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid5

from app.shared.domain.errors import ConflictError

_MISSION_NAMESPACE = UUID("c4a7e9b2-1d3f-4a58-9e60-7b2d8f1a0c35")


class MissionState(StrEnum):
    PENDING = "PENDIENTE"
    ANSWERED = "RESPONDIDA"


class MissionAnswer(StrEnum):
    CONFIRMS = "CONFIRMA"
    DISCARDS = "DESCARTA"


def mission_id(anomaly_id: UUID, user_id: UUID) -> UUID:
    """One mission per (anomaly, volunteer): the idempotency key of mission creation."""
    return uuid5(_MISSION_NAMESPACE, f"{anomaly_id}:{user_id}")


@dataclass(frozen=True, slots=True)
class Mission:
    id: UUID
    anomaly_id: UUID
    assigned_to: UUID
    radius_m: float
    created_at: datetime
    state: MissionState = MissionState.PENDING
    answer: MissionAnswer | None = None
    photo_path: str | None = None  # object path in the private bucket

    def answered(self, answer: MissionAnswer, photo_path: str | None) -> "Mission":
        """Copy carrying the answer. A mission can be answered exactly once."""
        if self.state is MissionState.ANSWERED:
            raise ConflictError("Ya respondiste esta misión.")
        return dataclasses.replace(
            self, state=MissionState.ANSWERED, answer=answer, photo_path=photo_path
        )


@dataclass(frozen=True, slots=True)
class MissionDetail:
    """A mission with the facts the volunteer needs to find the place (read model)."""

    mission: Mission
    zone_name: str
    anomaly_type: str
    hectares: float
    geometry: dict[str, Any]  # GeoJSON of the area to check
    before_image_path: str | None = None
    after_image_path: str | None = None
