import { Suspense } from "react";
import { MissionsView } from "@/features/missions/components/MissionsView";

export const metadata = { title: "Misiones · Vigía" };

export default function MissionsPage() {
  return (
    <div className="page page-wide">
      <h1>Misiones de verificación</h1>
      <p className="lede">
        Anomalías detectadas cerca de ti. Si puedes ir con seguridad, confirma o descarta lo que
        encuentres.
      </p>
      <Suspense fallback={<p role="status">Cargando…</p>}>
        <MissionsView />
      </Suspense>
    </div>
  );
}
