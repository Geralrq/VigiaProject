from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import ColumnElement, func

from app.monitoring.domain.geo import BBox

SRID = 4326


def intersects_bbox(column: ColumnElement, bbox: BBox) -> ColumnElement[bool]:
    # float() so integer bounds are never bound as ::INTEGER (which would truncate them)
    corners = (float(v) for v in (bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat))
    envelope = func.ST_MakeEnvelope(*corners, SRID)
    return func.ST_Intersects(column, envelope)


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def next_day_start(day: date) -> datetime:
    """Exclusive upper bound so `end` includes the whole day."""
    return day_start(day + timedelta(days=1))
