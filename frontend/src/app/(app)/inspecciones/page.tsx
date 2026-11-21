import { InspectionsBoard } from "@/features/inspections/components/InspectionsBoard";

export const metadata = { title: "Inspecciones · Vigía" };

export default function InspectionsPage() {
  return (
    <div className="page page-wide">
      <h1>Inspecciones</h1>
      <InspectionsBoard />
    </div>
  );
}
