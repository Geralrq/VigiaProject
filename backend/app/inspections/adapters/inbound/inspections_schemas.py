from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.inspections.application.use_cases.workflow import InspectionView
from app.inspections.domain.inspection import (
    MAX_AREA_HA,
    MAX_CAUSE_CHARS,
    MAX_FINDINGS_CHARS,
    MAX_PHOTOS,
    InspectionForm,
    InspectionState,
)


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tecnico_id: UUID


class FormIn(BaseModel):
    """The technician's form, validated at the edge. Every field is optional so a draft can
    be saved; closing the ticket requires all of them (and at least one photo)."""

    model_config = ConfigDict(extra="forbid")

    hallazgos: str | None = Field(default=None, max_length=MAX_FINDINGS_CHARS)
    causa_probable: str | None = Field(default=None, max_length=MAX_CAUSE_CHARS)
    area_verificada_ha: float | None = Field(default=None, ge=0, le=MAX_AREA_HA)
    fotos: list[str] = Field(
        default_factory=list,
        max_length=MAX_PHOTOS,
        description="Rutas devueltas por POST /fotos; solo fotos de este ticket",
    )

    def to_domain(self) -> InspectionForm:
        return InspectionForm(
            findings=(self.hallazgos or "").strip() or None,
            probable_cause=(self.causa_probable or "").strip() or None,
            verified_area_ha=self.area_verificada_ha,
            photos=tuple(self.fotos),
        )


class FormOut(BaseModel):
    hallazgos: str | None
    causa_probable: str | None
    area_verificada_ha: float | None
    fotos: list[str]
    completo: bool
    faltan: list[str]


class PhotoOut(BaseModel):
    path: str
    url: str | None  # signed, valid for 1 hour


class InspectionOut(BaseModel):
    id: UUID
    alert_id: UUID
    estado: InspectionState
    tecnico_id: UUID | None
    tecnico_nombre: str | None
    zona: str
    nivel_riesgo: str
    tipo_anomalia: str
    hectareas: float
    co2_estimado_t: float | None
    detectada_en: datetime
    creada_en: datetime
    cerrada_en: datetime | None
    ruta_google_maps: str = Field(description="Indicaciones hacia el centroide de la geocerca")
    formulario: FormOut | None
    fotos: list[PhotoOut]
    pdf_listo: bool

    @classmethod
    def from_view(cls, view: InspectionView) -> Self:
        d, i = view.detail, view.detail.inspection
        form = None
        if i.form is not None:
            missing = i.form.missing_fields()
            form = FormOut(
                hallazgos=i.form.findings,
                causa_probable=i.form.probable_cause,
                area_verificada_ha=i.form.verified_area_ha,
                fotos=list(i.form.photos),
                completo=not missing,
                faltan=missing,
            )
        return cls(
            id=i.id,
            alert_id=i.alert_id,
            estado=i.state,
            tecnico_id=i.technician_id,
            tecnico_nombre=d.technician_name,
            zona=d.zone_name,
            nivel_riesgo=d.risk_level,
            tipo_anomalia=d.anomaly_type,
            hectareas=d.hectares,
            co2_estimado_t=d.co2_tonnes,
            detectada_en=d.detected_at,
            creada_en=i.created_at,
            cerrada_en=i.closed_at,
            ruta_google_maps=view.route_url,
            formulario=form,
            fotos=[PhotoOut(path=p, url=view.photo_urls.get(p)) for p in i.photos],
            pdf_listo=i.pdf_path is not None,
        )


class PhotoUploaded(BaseModel):
    path: str = Field(description="Cítala en el formulario (campo fotos)")
    inspection: InspectionOut
