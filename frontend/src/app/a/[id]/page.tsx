import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPublicAlert } from "@/features/alerts/api/public-alert";
import { PublicAlertSheet } from "@/features/alerts/components/PublicAlertSheet";
import { ANOMALY_TYPE_LABELS, formatDate, formatNumber } from "@/features/map/labels";
import type { AnomalyType } from "@/shared/api/types";

// Pública y renderizada en servidor con datos frescos (sin caché ni guardas de sesión).
export const dynamic = "force-dynamic";

type Props = PageProps<"/a/[id]">;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const result = await getPublicAlert(id);
  if (result.kind !== "ok") return { title: "Alerta no disponible · Vigía", robots: { index: false } };

  const { alert } = result;
  const type = ANOMALY_TYPE_LABELS[alert.type as AnomalyType] ?? alert.type;
  const title = `Alerta de ${type.toLowerCase()} en ${alert.zone_name} · Vigía`;
  const description = `Riesgo ${alert.risk_level.toLowerCase()}, ${formatNumber(alert.hectares)} hectáreas afectadas, detectada el ${formatDate(alert.date)}.`;
  return {
    title,
    description,
    robots: { index: false }, // una alerta es información operativa, no contenido para buscadores
    openGraph: { title, description, type: "article", siteName: "Vigía", locale: "es_CO" },
    twitter: { card: "summary", title, description },
  };
}

export default async function PublicAlertPage({ params }: Props) {
  const { id } = await params;
  const result = await getPublicAlert(id);
  if (result.kind === "not-found") notFound();
  if (result.kind === "error") {
    return (
      <main className="auth-page">
        <p className="wordmark">Vigía</p>
        <h1>No pudimos cargar la alerta</h1>
        <p className="lede">El servicio no respondió. Recarga la página en unos minutos.</p>
        <p>
          <Link href={`/a/${id}`}>Reintentar</Link>
        </p>
      </main>
    );
  }
  return <PublicAlertSheet alert={result.alert} />;
}
