import { ReportForm } from "@/features/reports/components/ReportForm";

export const metadata = { title: "Reportar · Vigía" };

export default function ReportPage() {
  return (
    <div className="page">
      <h1>Reportar un problema ambiental</h1>
      <p className="lede">
        Cuéntanos qué viste. Con tu ubicación y, si puedes, una foto, las autoridades pueden
        actuar más rápido.
      </p>
      <ReportForm />
    </div>
  );
}
