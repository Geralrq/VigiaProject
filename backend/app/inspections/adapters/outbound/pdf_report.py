"""Inspection report as a PDF: ReportLab + qrcode + Pillow, entirely in memory (BytesIO).

Nothing is written to disk (Vercel's filesystem is read-only). Photos and satellite images
are shrunk to JPEG thumbnails so the file stays far below Vercel's 4.5 MB response limit:
if a first pass is above MAX_PDF_BYTES it is rebuilt with smaller / more compressed images.
Missing images become a marker box, never an error.
"""

import io
from xml.sax.saxutils import escape

import qrcode
from PIL import Image, ImageOps
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

from app.inspections.domain.report_data import IndexRow, InspectionReportData

rl_config.useA85 = 0  # raw DCT streams: ~25 % smaller than ASCII85-wrapped JPEGs

MAX_PDF_BYTES = 4_000_000  # Vercel caps responses at 4.5 MB
# (longest side in px, JPEG quality): tried in order until the PDF fits
IMAGE_PROFILES = ((720, 72), (480, 60), (320, 50))
MAX_SOURCE_PIXELS = 40_000_000  # refuse decompression bombs
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

RISK_COLORS = {
    "BAJO": "#2e7d32",
    "MEDIO": "#f9a825",
    "ALTO": "#ef6c00",
    "CRITICO": "#c62828",
}
RISK_LABEL = {"BAJO": "BAJO", "MEDIO": "MEDIO", "ALTO": "ALTO", "CRITICO": "CRÍTICO"}
TYPE_LABEL = {"DEFORESTACION": "Deforestación", "INCENDIO": "Incendio"}
STATE_LABEL = {
    "ABIERTO": "Abierto",
    "ASIGNADO": "Asignado",
    "EN_PROGRESO": "En progreso",
    "CERRADO": "Cerrado",
}
NO_DATA = "s/d"


def _t(text: object) -> str:
    """Safe Paragraph text: escaped markup, and only characters the built-in Helvetica can
    draw (Latin-1 / cp1252); anything else (emoji...) becomes '?'."""
    cleaned = str(text).encode("cp1252", "replace").decode("cp1252")
    return escape(cleaned)


def _num(value: float | None, fmt: str = "{:.3f}") -> str:
    return NO_DATA if value is None else fmt.format(value)


def _thumbnail(data: bytes | None, max_px: int, quality: int) -> tuple[io.BytesIO, int, int] | None:
    """JPEG thumbnail (RGB, transparency flattened onto white), or None if it cannot be read."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_SOURCE_PIXELS:
                return None
            source.draft("RGB", (max_px, max_px))  # cheap downscale while decoding JPEGs
            image = ImageOps.exif_transpose(source) or source
            if image.mode in ("RGBA", "LA", "P"):
                rgba = image.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                image = flat
            image = image.convert("RGB")
            image.thumbnail((max_px, max_px))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=quality, optimize=True)
            out.seek(0)
            return out, image.width, image.height
    except Exception:  # noqa: BLE001 - a corrupt or exotic image is a marker, not a failure
        return None


class ReportLabPdfGenerator:
    """ReportGeneratorPort implementation."""

    def generate(self, data: InspectionReportData) -> bytes:
        pdf = b""
        for max_px, quality in IMAGE_PROFILES:
            pdf = self._render(data, max_px, quality)
            if len(pdf) <= MAX_PDF_BYTES:
                break
        return pdf

    # --- document ---------------------------------------------------------------------------

    def _render(self, d: InspectionReportData, max_px: int, quality: int) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN + 6 * mm,
            title=_t(f"Informe de inspeccion - {d.zone_name}"),
            author="Vigia",
            pageCompression=0,
        )
        styles = _styles()

        def img(data: bytes | None, width: float, height: float, label: str):
            return self._image_cell(data, width, height, label, max_px, quality, styles)

        story: list = []
        story += self._cover(d, styles)
        story.append(PageBreak())
        story += self._satellite(d, styles, img)
        story += self._indices(d, styles)
        story += self._impact(d, styles)
        story += self._citizen(d, styles, img)
        story += self._technician(d, styles, img)

        def footer(canvas, document) -> None:
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.grey)
            canvas.drawString(
                MARGIN,
                10 * mm,
                _t(
                    f"Vigía · Informe de inspección {str(d.inspection_id)[:8]} · alerta {str(d.alert_id)[:8]}"
                ),
            )
            canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Página {document.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue()

    # --- sections ---------------------------------------------------------------------------

    def _cover(self, d: InspectionReportData, st: dict[str, ParagraphStyle]) -> list:
        color = colors.HexColor(RISK_COLORS.get(d.risk_level, "#455a64"))
        level = RISK_LABEL.get(d.risk_level, d.risk_level)
        banner = Table(
            [[Paragraph(_t(f"RIESGO {level}"), st["banner"])]],
            colWidths=[CONTENT_W],
            rowHeights=[22 * mm],
        )
        banner.setStyle(
            TableStyle(
                [("BACKGROUND", (0, 0), (-1, -1), color), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
            )
        )

        kind = TYPE_LABEL.get(d.anomaly_type, d.anomaly_type.capitalize())
        facts = [
            ["Zona", d.zone_name],
            ["Tipo de anomalía", kind],
            ["Fecha de detección", d.detected_at.strftime("%d/%m/%Y %H:%M UTC")],
            ["Confianza de la detección", f"{d.confidence * 100:.0f} %"],
            ["Estado del ticket", STATE_LABEL.get(d.state.value, d.state.value)],
            ["Informe generado", d.generated_at.strftime("%d/%m/%Y %H:%M UTC")],
        ]
        table = Table(
            [[Paragraph(_t(k), st["label"]), Paragraph(_t(v), st["body"])] for k, v in facts],
            colWidths=[55 * mm, CONTENT_W - 55 * mm],
        )
        table.setStyle(_grid_style())

        qr = self._qr(d.public_url)
        qr_row = Table(
            [
                [
                    qr,
                    Paragraph(
                        _t("Consulta la alerta en línea escaneando el código QR:")
                        + "<br/>"
                        + _t(d.public_url),
                        st["small"],
                    ),
                ]
            ],
            colWidths=[38 * mm, CONTENT_W - 38 * mm],
        )
        qr_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return [
            Paragraph("Informe de inspección ambiental", st["title"]),
            Spacer(1, 4 * mm),
            banner,
            Spacer(1, 8 * mm),
            table,
            Spacer(1, 10 * mm),
            qr_row,
        ]

    def _satellite(self, d, st, img) -> list:
        half = (CONTENT_W - 6 * mm) / 2
        cells = [
            [
                img(d.before_image, half, 62 * mm, "Imagen anterior no disponible"),
                "",
                img(d.after_image, half, 62 * mm, "Imagen posterior no disponible"),
            ],
            [
                Paragraph("Antes de la anomalía", st["caption"]),
                "",
                Paragraph("Después (detección)", st["caption"]),
            ],
        ]
        table = Table(cells, colWidths=[half, 6 * mm, half])
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return [
            Paragraph("Imágenes satelitales (Sentinel-2, color real)", st["h2"]),
            Paragraph(
                "Las zonas transparentes o vacías corresponden a nubes, sombras o falta de datos.",
                st["small"],
            ),
            Spacer(1, 2 * mm),
            table,
            Spacer(1, 6 * mm),
        ]

    def _indices(self, d, st) -> list:
        head = ["Índice", "Línea base (60 d)", "Reciente", "Variación"]
        rows = [[Paragraph(_t(h), st["label"]) for h in head]]
        ndvi: IndexRow | None = None
        for r in d.index_rows:
            if r.name == "NDVI":
                ndvi = r
            rows.append(
                [Paragraph(_t(r.name), st["body"])]
                + [
                    Paragraph(_t(v), st["body"])
                    for v in (_num(r.baseline), _num(r.current), _num(r.delta, "{:+.3f}"))
                ]
            )
        out: list = [Paragraph("Índices espectrales", st["h2"])]
        if len(rows) == 1:
            out.append(
                Paragraph("[Sin lecturas de índices disponibles para esta zona]", st["marker"])
            )
        else:
            table = Table(rows, colWidths=[35 * mm, 45 * mm, 40 * mm, CONTENT_W - 120 * mm])
            table.setStyle(_grid_style(header=True))
            out.append(table)
            if ndvi and ndvi.delta is not None:
                trend = "caída" if ndvi.delta < 0 else "aumento"
                out.append(Spacer(1, 2 * mm))
                out.append(
                    Paragraph(
                        _t(
                            f"Variación de NDVI respecto a la línea base: {ndvi.delta:+.3f} ({trend})"
                        ),
                        st["body"],
                    )
                )
        return [*out, Spacer(1, 6 * mm)]

    def _impact(self, d, st) -> list:
        co2 = (
            f"{d.co2_tonnes:,.1f} t CO2e".replace(",", " ")
            if d.co2_tonnes is not None
            else "No disponible (sin factor de carbono para esta cobertura)"
        )
        rows = [
            ["Área afectada (estimada)", f"{d.hectares:,.1f} ha".replace(",", " ")],
            ["CO2 liberado (ESTIMACIÓN)", co2],
        ]
        table = Table(
            [[Paragraph(_t(k), st["label"]), Paragraph(_t(v), st["body"])] for k, v in rows],
            colWidths=[55 * mm, CONTENT_W - 55 * mm],
        )
        table.setStyle(_grid_style())
        note = Paragraph(
            _t(
                "Las cifras son estimaciones: hectáreas = píxeles afectados × 0,01; CO2 = hectáreas × tC/ha de la cobertura × 3,67. No son mediciones directas."
            ),
            st["small"],
        )
        return [
            Paragraph("Impacto estimado", st["h2"]),
            table,
            Spacer(1, 2 * mm),
            note,
            Spacer(1, 6 * mm),
        ]

    def _citizen(self, d, st, img) -> list:
        out: list = [Paragraph("Verificación ciudadana", st["h2"])]
        if not d.citizen_photos:
            out.append(Paragraph("[Sin fotos de verificación ciudadana]", st["marker"]))
            return [*out, Spacer(1, 6 * mm)]
        out.append(
            Paragraph(
                _t(f"{len(d.citizen_photos)} foto(s) enviada(s) por voluntarios en terreno."),
                st["small"],
            )
        )
        out.append(Spacer(1, 2 * mm))
        out.append(self._grid([img(p, 40 * mm, 40 * mm, "") for p in d.citizen_photos[:4]], cols=4))
        return [*out, Spacer(1, 6 * mm)]

    def _technician(self, d, st, img) -> list:
        out: list = [CondPageBreak(70 * mm), Paragraph("Inspección técnica", st["h2"])]
        form = d.form
        if form is None:
            out.append(Paragraph("[Aún no hay formulario del técnico]", st["marker"]))
            return out
        rows = [
            ["Técnico", d.technician_name or NO_DATA],
            ["Hallazgos", form.findings or NO_DATA],
            ["Causa probable", form.probable_cause or NO_DATA],
            [
                "Área verificada",
                NO_DATA
                if form.verified_area_ha is None
                else f"{form.verified_area_ha:,.1f} ha".replace(",", " "),
            ],
        ]
        table = Table(
            [
                [Paragraph(_t(k), st["label"]), Paragraph(_t(v).replace("\n", "<br/>"), st["body"])]
                for k, v in rows
            ],
            colWidths=[40 * mm, CONTENT_W - 40 * mm],
        )
        table.setStyle(_grid_style())
        out += [table, Spacer(1, 4 * mm)]
        if d.technician_photos:
            out.append(Paragraph("Fotos del técnico", st["label"]))
            out.append(Spacer(1, 2 * mm))
            out.append(
                self._grid(
                    [img(p, 52 * mm, 45 * mm, "Foto no disponible") for p in d.technician_photos],
                    cols=3,
                )
            )
        else:
            out.append(Paragraph("[Sin fotos del técnico]", st["marker"]))
        return out

    # --- helpers ---------------------------------------------------------------------------

    def _grid(self, cells: list, cols: int) -> Table:
        rows = [cells[i : i + cols] for i in range(0, len(cells), cols)]
        for row in rows:
            row += [""] * (cols - len(row))
        table = Table(rows, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _image_cell(self, data, width, height, label, max_px, quality, st):
        """The photo scaled into width x height, or a marker box when it is missing."""
        thumb = _thumbnail(data, max_px, quality)
        if thumb is None:
            box = Table(
                [[Paragraph(_t(f"[{label or 'Foto no disponible'}]"), st["marker_c"])]],
                colWidths=[width],
                rowHeights=[height],
            )
            box.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                    ]
                )
            )
            return box
        buf, w, h = thumb
        scale = min(width / w, height / h)
        return RLImage(buf, width=w * scale, height=h * scale)

    def _qr(self, url: str) -> RLImage:
        code = qrcode.make(url, box_size=6, border=2)
        buf = io.BytesIO()
        code.save(buf)
        buf.seek(0)
        return RLImage(buf, width=34 * mm, height=34 * mm)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=12.5)
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=22, leading=26, alignment=0
        ),
        "banner": ParagraphStyle(
            "banner",
            parent=body,
            fontSize=24,
            leading=28,
            textColor=colors.white,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=14,
            spaceBefore=4,
            spaceAfter=4,
            textColor=colors.HexColor("#1b5e20"),
        ),
        "body": body,
        "label": ParagraphStyle("label", parent=body, fontName="Helvetica-Bold"),
        "small": ParagraphStyle(
            "small", parent=body, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555")
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=body,
            fontSize=8.5,
            textColor=colors.HexColor("#555555"),
            alignment=TA_CENTER,
        ),
        "marker": ParagraphStyle(
            "marker",
            parent=body,
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#777777"),
        ),
        "marker_c": ParagraphStyle(
            "marker_c",
            parent=body,
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#777777"),
            alignment=TA_CENTER,
        ),
    }


def _grid_style(header: bool = False) -> TableStyle:
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd8dc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f8e9"))
        if not header
        else ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f8e9")),
    ]
    return TableStyle(commands)


__all__ = ["MAX_PDF_BYTES", "ReportLabPdfGenerator"]
