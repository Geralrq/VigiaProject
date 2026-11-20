"""Pure rules of the citizen verification of an anomaly."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.reports.domain.mission import MissionAnswer

REQUIRED_AGREEMENT = 2  # matching answers that settle the question
MAX_MISSIONS = 5  # volunteers asked per anomaly


class ReviewState(StrEnum):
    """The anomaly's state as verification sees it (monitoring's AnomalyState values)."""

    DETECTED = "DETECTADA"
    IN_REVIEW = "EN_VERIFICACION"
    CONFIRMED = "CONFIRMADA"
    FALSE_POSITIVE = "FALSO_POSITIVO"


OPEN_STATES = frozenset({ReviewState.DETECTED, ReviewState.IN_REVIEW})


class Outcome(StrEnum):
    CONFIRMED = "CONFIRMADA"
    DISCARDED = "FALSO_POSITIVO"


def decide(answers: Iterable[MissionAnswer]) -> Outcome | None:
    """2 CONFIRMA => confirmed; 2 DESCARTA => discarded; otherwise still open.

    (Both sides reaching 2 cannot happen when decisions are taken after every answer; if it
    ever did, the question stays open rather than picking a side.)
    """
    answers = list(answers)
    confirms = answers.count(MissionAnswer.CONFIRMS)
    discards = answers.count(MissionAnswer.DISCARDS)
    if confirms >= REQUIRED_AGREEMENT and discards >= REQUIRED_AGREEMENT:
        return None
    if confirms >= REQUIRED_AGREEMENT:
        return Outcome.CONFIRMED
    if discards >= REQUIRED_AGREEMENT:
        return Outcome.DISCARDED
    return None


def outcome_of(state: ReviewState) -> Outcome | None:
    """The final outcome an anomaly state stands for (None while it is still open)."""
    return {
        ReviewState.CONFIRMED: Outcome.CONFIRMED,
        ReviewState.FALSE_POSITIVE: Outcome.DISCARDED,
    }.get(state)


def matches(answer: MissionAnswer, outcome: Outcome) -> bool:
    return (answer is MissionAnswer.CONFIRMS) == (outcome is Outcome.CONFIRMED)


@dataclass(frozen=True, slots=True)
class MissionCandidate:
    user_id: UUID
    distance_m: float  # to the nearest point of the affected area (0 if inside)
    telegram_chat_id: int | None = None


def select_nearest(
    candidates: Sequence[MissionCandidate], radius_m: float, limit: int = MAX_MISSIONS
) -> list[MissionCandidate]:
    """The `limit` nearest volunteers within `radius_m`, once each, nearest first.

    Ties break by user id so the choice is deterministic.
    """
    unique: dict[UUID, MissionCandidate] = {}
    for c in candidates:
        if c.distance_m <= radius_m and (
            c.user_id not in unique or c.distance_m < unique[c.user_id].distance_m
        ):
            unique[c.user_id] = c
    ordered = sorted(unique.values(), key=lambda c: (c.distance_m, str(c.user_id)))
    return ordered[:limit]
