"""Everything the PDF needs, already gathered. The generator only lays it out."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.inspections.domain.inspection import InspectionForm, InspectionState

MAX_CITIZEN_PHOTOS = 4
MAX_TECHNICIAN_PHOTOS = 6


@dataclass(frozen=True, slots=True)
class IndexRow:
    """One spectral index: 60-day baseline, recent value and the change (negative = drop)."""

    name: str
    baseline: float | None
    current: float | None
    delta: float | None


@dataclass(frozen=True, slots=True)
class InspectionReportData:
    """Missing pieces are None / empty: the generator prints a marker instead of failing."""

    inspection_id: UUID
    alert_id: UUID
    state: InspectionState
    risk_level: str
    zone_name: str
    anomaly_type: str
    confidence: float
    detected_at: datetime
    hectares: float
    co2_tonnes: float | None
    public_url: str  # the QR code points here: <PUBLIC_APP_URL>/a/<alert_id>
    generated_at: datetime
    index_rows: list[IndexRow] = field(default_factory=list)
    before_image: bytes | None = None
    after_image: bytes | None = None
    citizen_photos: list[bytes] = field(default_factory=list)  # at most MAX_CITIZEN_PHOTOS
    technician_name: str | None = None
    form: InspectionForm | None = None
    technician_photos: list[bytes | None] = field(default_factory=list)  # None = not available
