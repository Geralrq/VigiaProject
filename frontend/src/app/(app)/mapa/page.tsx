import { Suspense } from "react";
import { CommandCenter } from "@/features/map/components/CommandCenter";
import { Skeleton } from "@/shared/ui/states";

export const metadata = { title: "Centro de comando · Vigía" };

export default function MapPage() {
  // Suspense: el centro de comando lee capas y selección de la URL (useSearchParams).
  return (
    <Suspense fallback={<Skeleton label="Cargando el centro de comando…" variant="block" />}>
      <CommandCenter />
    </Suspense>
  );
}
