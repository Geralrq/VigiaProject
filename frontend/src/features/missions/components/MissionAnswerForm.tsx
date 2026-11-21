"use client";

import { useState, type FormEvent } from "react";
import type { MissionAnswer, MissionAnswerResult } from "@/shared/api/types";
import { usePhotoPicker } from "@/shared/hooks/usePhotoPicker";
import { ChoiceGroup } from "@/shared/ui/fields";
import { PhotoField } from "@/shared/ui/PhotoField";
import { useRespondToMission } from "../api/queries";

const ANSWER_OPTIONS = [
  { value: "CONFIRMA", label: "Sí, hay un problema", hint: "confirmo la anomalía" },
  { value: "DESCARTA", label: "No, es una falsa alarma", hint: "descarto la anomalía" },
] as const satisfies readonly { value: MissionAnswer; label: string; hint: string }[];

/** Responde una misión pendiente. Solo se puede responder una vez. */
export function MissionAnswerForm({
  missionId,
  onAnswered,
}: {
  missionId: string;
  onAnswered: (result: MissionAnswerResult) => void;
}) {
  const respond = useRespondToMission();
  const photo = usePhotoPicker();
  const [answer, setAnswer] = useState<MissionAnswer | null>(null);
  const [missing, setMissing] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!answer) {
      setMissing(true);
      return;
    }
    respond.mutate({ missionId, answer, photo: photo.file }, { onSuccess: onAnswered });
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Responder la misión">
      <ChoiceGroup
        legend="¿Qué encontraste en el lugar?"
        name="answer"
        value={answer ?? ("" as MissionAnswer)}
        options={ANSWER_OPTIONS}
        onChange={(value) => {
          setAnswer(value);
          setMissing(false);
        }}
      />
      {missing && (
        <p role="alert" className="error">
          Elige una respuesta antes de enviar.
        </p>
      )}
      <PhotoField
        label="Foto del lugar (opcional)"
        picker={photo}
        previewAlt="Vista previa de la foto del lugar"
        hint="Ayuda a las autoridades a decidir."
      />
      {respond.isError && (
        <p role="alert" className="error">
          {respond.error.message}
        </p>
      )}
      <button
        type="submit"
        className="primary"
        disabled={respond.isPending || photo.busy}
        aria-busy={respond.isPending}
      >
        {respond.isPending ? "Enviando respuesta…" : "Enviar respuesta"}
      </button>
    </form>
  );
}
