"use client";

import Link from "next/link";
import {
  ANOMALY_STATE_LABELS,
  ANOMALY_TYPE_LABELS,
  formatDate,
  formatNumber,
} from "@/features/map/labels";
import type { AnomalyType, Mission, MissionAnswerResult } from "@/shared/api/types";
import { geometryCenter, googleMapsUrl } from "@/shared/geo";
import { MissionAnswerForm } from "./MissionAnswerForm";

const ANSWER_LABELS = { CONFIRMA: "Confirmaste el problema", DESCARTA: "Lo descartaste" } as const;

interface Props {
  mission: Mission;
  result: MissionAnswerResult | undefined;
  onAnswered: (result: MissionAnswerResult) => void;
}

export function MissionDetail({ mission, result, onAnswered }: Props) {
  const center = geometryCenter(mission.geometry);
  const typeLabel = ANOMALY_TYPE_LABELS[mission.anomaly_type as AnomalyType] ?? mission.anomaly_type;

  return (
    <article aria-labelledby="mission-title">
      <p>
        <Link href="/misiones" className="back-link">
          Volver a la lista
        </Link>
      </p>
      <h2 id="mission-title">
        {typeLabel} en {mission.zone_name}
      </h2>

      <dl className="facts">
        <dt>Estado</dt>
        <dd>{mission.state === "PENDIENTE" ? "Pendiente de tu respuesta" : "Respondida"}</dd>
        <dt>Superficie</dt>
        <dd>{formatNumber(mission.hectares)}&nbsp;hectáreas</dd>
        <dt>Cerca de ti</dt>
        <dd>a menos de {formatNumber(mission.radius_m / 1000)}&nbsp;km</dd>
        <dt>Asignada</dt>
        <dd>
          <time dateTime={mission.created_at}>{formatDate(mission.created_at)}</time>
        </dd>
        {center && (
          <>
            <dt>Ubicación</dt>
            <dd>
              <span className="mono">
                {center.lat.toFixed(4)}, {center.lng.toFixed(4)}
              </span>
            </dd>
          </>
        )}
      </dl>

      {center && (
        <p>
          <a
            className="button"
            href={googleMapsUrl(center)}
            target="_blank"
            rel="noopener noreferrer"
          >
            Abrir en Google Maps
          </a>
        </p>
      )}

      {mission.before_image_url && mission.after_image_url && (
        <section aria-label="Imágenes satelitales">
          <h3>Imágenes satelitales</h3>
          <div className="image-pair">
            <figure>
              {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
              <img src={mission.before_image_url} alt="Imagen satelital de antes" width={384} height={384} loading="lazy" />
              <figcaption className="muted">Antes</figcaption>
            </figure>
            <figure>
              {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
              <img src={mission.after_image_url} alt="Imagen satelital de después" width={384} height={384} loading="lazy" />
              <figcaption className="muted">Después</figcaption>
            </figure>
          </div>
        </section>
      )}

      {result ? (
        <section aria-label="Resultado" role="status">
          <h3>Respuesta enviada</h3>
          <p className="impact-figure">+{result.points_awarded} puntos</p>
          <p>
            {result.anomaly_state
              ? `La anomalía quedó como: ${ANOMALY_STATE_LABELS[result.anomaly_state]}. `
              : "Tu respuesta quedó registrada. "}
            Los puntos de coincidencia se suman cuando se decide el resultado.
          </p>
          <p>
            <Link href="/ranking">Ver el ranking</Link>
          </p>
        </section>
      ) : mission.state === "PENDIENTE" ? (
        <section aria-label="Responder">
          <h3>Tu respuesta</h3>
          <MissionAnswerForm key={mission.id} missionId={mission.id} onAnswered={onAnswered} />
        </section>
      ) : (
        <section aria-label="Tu respuesta">
          <h3>Tu respuesta</h3>
          <p>{mission.answer ? ANSWER_LABELS[mission.answer] : "Respondida."}</p>
          {mission.photo_url && (
            <figure>
              {/* eslint-disable-next-line @next/next/no-img-element -- URL firmada externa */}
              <img src={mission.photo_url} alt="Tu foto del lugar" width={384} height={288} loading="lazy" />
            </figure>
          )}
        </section>
      )}
    </article>
  );
}
