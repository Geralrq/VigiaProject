"use client";

import { saveBlob } from "@/shared/ui/download";
import { useInspectionPdf } from "../api/queries";

/** Descarga el informe PDF. Puede tardar unos segundos la primera vez (se genera al pedirlo). */
export function PdfButton({ inspectionId }: { inspectionId: string }) {
  const pdf = useInspectionPdf(inspectionId);
  return (
    <div>
      <button
        type="button"
        disabled={pdf.isPending}
        aria-busy={pdf.isPending}
        onClick={() =>
          pdf.mutate(undefined, { onSuccess: (blob) => saveBlob(blob, `informe-${inspectionId}.pdf`) })
        }
      >
        {pdf.isPending ? "Generando informe…" : "Descargar informe PDF"}
      </button>
      {pdf.isError && (
        <p role="alert" className="error">
          {pdf.error.message}
        </p>
      )}
    </div>
  );
}
