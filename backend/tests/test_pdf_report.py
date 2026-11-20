"""The real ReportLab generator and the report use case's tolerance to missing evidence."""

import builtins
import io
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from PIL import Image

from app.inspections.adapters.outbound.pdf_report import (
    MAX_PDF_BYTES,
    ReportLabPdfGenerator,
    _t,
    _thumbnail,
)
from app.inspections.application.ports.inspection_ports import SatelliteImagePaths
from app.inspections.application.use_cases.inspection_pdf import GenerateInspectionPdf, report_path
from app.inspections.domain.inspection import Inspection, InspectionForm, InspectionState
from app.inspections.domain.report_data import IndexRow, InspectionReportData
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.errors import NotFoundError, ServiceUnavailableError
from tests.fakes_inspections import FakeEvidenceSource, FakePdfGenerator

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
FORM = InspectionForm("Tala de unas 12 ha", "Expansión de pastizal", 11.5, ("a", "b"))


def image_bytes(size=(640, 480), fmt="PNG", mode="RGB", noisy=False) -> bytes:
    shade = os.urandom(3)  # distinct images: ReportLab stores identical ones only once
    colour = (shade[0], shade[1], shade[2]) if mode == "RGB" else (shade[0], shade[1], shade[2], 0)
    img = (
        Image.frombytes(mode, size, os.urandom(size[0] * size[1] * len(mode)))
        if noisy
        else Image.new(mode, size, colour)
    )
    out = io.BytesIO()
    img.save(out, format=fmt, **({"quality": 95} if fmt == "JPEG" else {}))
    return out.getvalue()


def report_data(**overrides) -> InspectionReportData:
    base = {
        "inspection_id": uuid4(),
        "alert_id": uuid4(),
        "state": InspectionState.CLOSED,
        "risk_level": "CRITICO",
        "zone_name": "Amazonía – frente de deforestación (Guaviare)",
        "anomaly_type": "DEFORESTACION",
        "confidence": 0.87,
        "detected_at": NOW,
        "hectares": 120.0,
        "co2_tonnes": 79_200.0,
        "public_url": "https://vigia.example/a/abc",
        "generated_at": NOW,
        "index_rows": [
            IndexRow("NDVI", 0.82, 0.41, -0.41),
            IndexRow("NBR", 0.62, 0.30, -0.32),
            IndexRow("NDWI", None, None, None),
        ],
        "before_image": image_bytes(mode="RGBA"),
        "after_image": image_bytes(fmt="JPEG"),
        "citizen_photos": [image_bytes() for _ in range(4)],
        "technician_name": "Tina Técnica",
        "form": FORM,
        "technician_photos": [image_bytes(fmt="JPEG"), None],
    }
    return InspectionReportData(**(base | overrides))


def raw(text: str) -> bytes:
    """How ReportLab writes `text` in a content stream: cp1252 with octal escapes above ASCII."""
    out = []
    for ch in text:
        code = ch.encode("cp1252")[0]
        out.append(ch if code < 128 else rf"\{code:03o}")
    return "".join(out).replace("(", r"\(").replace(")", r"\)").encode("ascii")


MINIMAL = {
    "index_rows": [],
    "before_image": None,
    "after_image": None,
    "citizen_photos": [],
    "form": None,
    "technician_photos": [],
    "technician_name": None,
    "co2_tonnes": None,
}


# --- the generator ----------------------------------------------------------------------------------


def test_a_full_report_is_a_small_valid_pdf() -> None:
    pdf = ReportLabPdfGenerator().generate(report_data())
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
    assert 10_000 < len(pdf) < MAX_PDF_BYTES


def test_the_report_contains_the_required_sections() -> None:
    d = report_data()
    pdf = ReportLabPdfGenerator().generate(d)  # uncompressed text streams: searchable
    for needle in (
        raw("RIESGO CRÍTICO"),  # cover: risk level
        raw("Guaviare"),  # zone
        raw("19/11/2026"),  # date
        raw("Imágenes satelitales"),
        raw("Índices espectrales"),
        raw("-0.410"),  # NDVI change
        raw("CO2 liberado (ESTIMACIÓN)"),  # CO2 is labelled an estimate
        raw("Verificación ciudadana"),
        raw("Inspección técnica"),
        raw("Tina Técnica"),
        raw("Expansión de pastizal"),
        raw("vigia.example/a/abc"),  # the QR's target is also printed
    ):
        assert needle in pdf, needle
    assert (
        pdf.count(b"/Subtype /Image") >= 1 + 2 + 4 + 1
    )  # QR, before/after, 4 citizen, 1 technician photo (the other is a marker)


def test_missing_everything_still_produces_a_report_with_markers() -> None:
    pdf = ReportLabPdfGenerator().generate(report_data(**MINIMAL))
    assert pdf.startswith(b"%PDF")
    for marker in (
        raw("[Imagen anterior no disponible]"),
        raw("[Imagen posterior no disponible]"),
        raw("[Sin lecturas de índices"),
        raw("[Sin fotos de verificación ciudadana]"),
        raw("[Aún no hay formulario del técnico]"),
        raw("No disponible (sin factor de carbono"),
    ):
        assert marker in pdf, marker


def test_a_form_without_photos_or_with_unavailable_photos_prints_markers() -> None:
    pdf = ReportLabPdfGenerator().generate(
        report_data(form=InspectionForm(findings="Solo hallazgos"), technician_photos=[None, None])
    )
    assert pdf.count(raw("[Foto no disponible]")) == 2 and b"s/d" in pdf


@pytest.mark.parametrize(
    "junk", [b"not an image", b"\x89PNG\r\n\x1a\n" + b"\x00" * 10, b"", b"GIF89a"]
)
def test_corrupt_images_become_markers_not_errors(junk: bytes) -> None:
    pdf = ReportLabPdfGenerator().generate(
        report_data(
            before_image=junk, after_image=junk, citizen_photos=[junk], technician_photos=[junk]
        )
    )
    assert pdf.startswith(b"%PDF") and raw("[Imagen anterior no disponible]") in pdf


def test_large_photos_are_shrunk_so_the_pdf_stays_under_the_limit() -> None:
    big = [image_bytes((2600, 1900), "JPEG", noisy=True) for _ in range(8)]
    assert sum(map(len, big)) > 20_000_000  # ~20 MB of source images
    data = report_data(
        before_image=big[0], after_image=big[1], citizen_photos=big[2:6], technician_photos=big[6:8]
    )

    pdf = ReportLabPdfGenerator().generate(data)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) <= MAX_PDF_BYTES < 4_500_000  # Vercel's response cap


def test_the_pdf_falls_back_to_smaller_images_when_the_first_pass_is_too_big(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.inspections.adapters.outbound.pdf_report.MAX_PDF_BYTES", 1_000
    )  # unreachable: forces every fallback
    sizes = []
    original = ReportLabPdfGenerator._render

    def spy(self, d, max_px, quality):
        sizes.append((max_px, quality))
        return original(self, d, max_px, quality)

    monkeypatch.setattr(ReportLabPdfGenerator, "_render", spy)
    big = [image_bytes((2000, 1500), "JPEG", noisy=True) for _ in range(3)]
    pdf = ReportLabPdfGenerator().generate(
        report_data(before_image=big[0], after_image=big[1], citizen_photos=big[2:])
    )
    assert pdf.startswith(b"%PDF")
    assert sizes == [(720, 72), (480, 60), (320, 50)]  # tried every profile, smallest last


def test_thumbnails_are_rgb_jpegs_with_transparency_flattened() -> None:
    thumb = _thumbnail(image_bytes((1200, 800), mode="RGBA"), 400, 60)
    assert thumb is not None
    buf, w, h = thumb
    image = Image.open(buf)
    assert image.format == "JPEG" and image.mode == "RGB" and max(w, h) == 400
    assert (
        image.getpixel((5, 5)) == (255, 255, 255) or sum(image.getpixel((5, 5))) > 700
    )  # cloud = white
    assert _thumbnail(b"junk", 400, 60) is None and _thumbnail(None, 400, 60) is None


def test_text_is_escaped_and_restricted_to_what_helvetica_can_draw() -> None:
    assert _t("a < b & c") == "a &lt; b &amp; c"
    assert _t("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"  # user text can never inject markup
    assert _t("Tala 🔥 ñandú") == "Tala ? ñandú"
    pdf = ReportLabPdfGenerator().generate(
        report_data(zone_name="Zona <b>&</b> 🔥", form=InspectionForm(findings="a < b <i>c</i> 🔥"))
    )
    assert pdf.startswith(b"%PDF")


def test_generating_a_report_never_writes_to_disk(monkeypatch, tmp_path) -> None:
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
            raise AssertionError(f"disk write attempted: {file!r} ({mode})")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.chdir(tmp_path)
    before = set(os.listdir(tmp_path))

    pdf = ReportLabPdfGenerator().generate(report_data())

    assert pdf.startswith(b"%PDF")
    assert set(os.listdir(tmp_path)) == before == set()


# --- the use case: tolerant gathering ---------------------------------------------------------------


class Repo:
    """Just enough InspectionRepository for the use case."""

    def __init__(self, detail) -> None:
        self.detail = detail
        self.saved_path: str | None = None

    def get_detail(self, inspection_id):
        return self.detail

    def set_pdf_path(self, inspection_id, path) -> None:
        self.saved_path = path


def make_use_case(
    *, storage=None, evidence=None, generator=None, pdf_path=None, form=FORM, photos=("p1", "p2")
):
    from app.inspections.domain.inspection import InspectionDetail

    inspection = Inspection(
        uuid4(), uuid4(), NOW, InspectionState.IN_PROGRESS, uuid4(), form, tuple(photos), pdf_path
    )
    detail = InspectionDetail(
        inspection,
        uuid4(),
        "Guaviare",
        uuid4(),
        "DEFORESTACION",
        "ALTO",
        0.9,
        12.0,
        None,
        NOW,
        {"type": "Polygon", "coordinates": []},
        "Tina",
    )
    repo = Repo(detail)
    storage = storage or InMemoryStorage()
    evidence = evidence or FakeEvidenceSource()
    generator = generator or FakePdfGenerator()
    use_case = GenerateInspectionPdf(
        repo, evidence, storage, generator, "https://vigia.example/", clock=lambda: NOW
    )
    return use_case, repo, storage, evidence, generator, inspection


async def test_everything_failing_still_yields_a_report() -> None:
    evidence = FakeEvidenceSource()
    evidence.fail_images = evidence.fail_readings = evidence.fail_citizen = True
    use_case, repo, storage, _, generator, inspection = make_use_case(evidence=evidence)

    pdf = await use_case.execute(inspection.id)

    assert pdf.startswith(b"%PDF")
    [data] = generator.calls
    assert (data.before_image, data.after_image, data.citizen_photos, data.index_rows) == (
        None,
        None,
        [],
        [],
    )
    assert data.technician_photos == [None, None]  # photos are listed, as unavailable markers
    assert (
        repo.saved_path == report_path(inspection.id)
        and report_path(inspection.id) in storage.objects
    )


async def test_missing_objects_in_storage_are_skipped_or_marked() -> None:
    storage = InMemoryStorage()
    storage.objects["p1"] = (b"PHOTO1", "image/png")  # p2 is gone
    storage.objects["c1"] = (b"C1", "image/png")
    evidence = FakeEvidenceSource()
    evidence.images = SatelliteImagePaths("nope/antes.png", None)
    evidence.citizen_paths = ["gone", "c1"]
    use_case, _, _, _, generator, inspection = make_use_case(
        storage=storage, evidence=evidence, form=InspectionForm("x", "y", 1.0, ("p1", "p2"))
    )

    await use_case.execute(inspection.id)

    data = generator.calls[0]
    assert data.before_image is None and data.citizen_photos == [b"C1"]
    assert data.technician_photos == [b"PHOTO1", None]


async def test_at_most_four_citizen_and_six_technician_photos_are_used() -> None:
    storage = InMemoryStorage()
    paths = [f"p{i}" for i in range(10)]
    for p in paths:
        storage.objects[p] = (p.encode(), "image/png")
    evidence = FakeEvidenceSource()
    evidence.citizen_paths = paths
    form = InspectionForm("x", "y", 1.0, tuple(paths))
    use_case, _, _, _, generator, inspection = make_use_case(
        storage=storage, evidence=evidence, form=form, photos=paths
    )

    await use_case.execute(inspection.id)

    data = generator.calls[0]
    assert len(data.citizen_photos) == 4 and len(data.technician_photos) == 6


async def test_without_a_form_the_uploaded_photos_are_still_listed() -> None:
    use_case, _, _, _, generator, inspection = make_use_case(form=None, photos=("p1",))
    await use_case.execute(inspection.id)
    assert generator.calls[0].form is None and generator.calls[0].technician_photos == [None]


async def test_a_cached_pdf_is_returned_without_regenerating_unless_forced() -> None:
    storage = InMemoryStorage()
    storage.objects["informes/x.pdf"] = (b"%PDF-cached", "application/pdf")
    use_case, _, _, _, generator, inspection = make_use_case(
        storage=storage, pdf_path="informes/x.pdf"
    )

    assert await use_case.execute(inspection.id) == b"%PDF-cached"
    assert generator.calls == []
    forced = await use_case.execute(inspection.id, force=True)
    assert forced != b"%PDF-cached" and len(generator.calls) == 1


async def test_a_storage_failure_while_saving_does_not_lose_the_report() -> None:
    class FlakyStorage(InMemoryStorage):
        def upload(self, *a, **k):
            raise ServiceUnavailableError("down")

    use_case, repo, _, _, _, inspection = make_use_case(storage=FlakyStorage())
    pdf = await use_case.execute(inspection.id)
    assert pdf.startswith(b"%PDF") and repo.saved_path is None


async def test_the_public_link_in_the_qr_uses_the_configured_app_url() -> None:
    use_case, _, _, _, generator, inspection = make_use_case()
    await use_case.execute(inspection.id)
    assert generator.calls[0].public_url == f"https://vigia.example/a/{inspection.alert_id}"


async def test_unknown_ticket_is_not_found() -> None:
    use_case, repo, *_ = make_use_case()
    repo.detail = None
    with pytest.raises(NotFoundError):
        await use_case.execute(uuid4())
