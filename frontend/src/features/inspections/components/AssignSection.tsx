"use client";

import { useState, type FormEvent } from "react";
import type { Inspection } from "@/shared/api/types";
import { SelectField } from "@/shared/ui/fields";
import { useAssignInspection, useTechnicians } from "../api/queries";

/** AUTORIDAD y ADMIN: asigna (o reasigna) el ticket a un técnico. */
export function AssignSection({ inspection }: { inspection: Inspection }) {
  const technicians = useTechnicians(true);
  const assign = useAssignInspection(inspection.id);
  const [chosen, setChosen] = useState(inspection.tecnico_id ?? "");
  const [missing, setMissing] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!chosen) {
      setMissing(true);
      return;
    }
    assign.mutate(chosen);
  }

  return (
    <section aria-labelledby="assign-title">
      <h2 id="assign-title">Asignación</h2>
      {technicians.isPending && <p role="status">Cargando técnicos…</p>}
      {technicians.isError && (
        <p role="alert" className="error">
          {technicians.error.message}
        </p>
      )}
      {technicians.data && technicians.data.length === 0 && (
        <p>No hay técnicos registrados para asignar.</p>
      )}
      {technicians.data && technicians.data.length > 0 && (
        <form onSubmit={onSubmit} noValidate aria-label="Asignar a un técnico">
          <SelectField
            label="Técnico"
            name="tecnico"
            value={chosen}
            error={missing ? "Elige un técnico." : null}
            onChange={(e) => {
              setChosen(e.target.value);
              setMissing(false);
            }}
          >
            <option value="">Elige un técnico</option>
            {technicians.data.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </SelectField>
          {assign.isSuccess && <p role="status">Inspección asignada. Se avisó al técnico.</p>}
          {assign.isError && (
            <p role="alert" className="error">
              {assign.error.message}
            </p>
          )}
          <button type="submit" className="primary" disabled={assign.isPending} aria-busy={assign.isPending}>
            {assign.isPending ? "Asignando…" : inspection.tecnico_id ? "Reasignar" : "Asignar"}
          </button>
        </form>
      )}
    </section>
  );
}
