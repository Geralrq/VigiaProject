"use client";

import { use } from "react";
import { InspectionDetail } from "@/features/inspections/components/InspectionDetail";

export default function InspectionPage({ params }: PageProps<"/inspecciones/[id]">) {
  const { id } = use(params);
  return (
    <div className="page">
      <InspectionDetail id={id} />
    </div>
  );
}
