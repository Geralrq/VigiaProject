import { UsersAdmin } from "@/features/admin/components/UsersAdmin";

export const metadata = { title: "Usuarios · Vigía" };

export default function AdminUsersPage() {
  return (
    <div className="page page-wide">
      <h1>Usuarios</h1>
      <p className="lede">
        Busca cuentas y asigna su rol. De cada persona solo se muestra si compartió su ubicación o
        vinculó Telegram, nunca los datos.
      </p>
      <UsersAdmin />
    </div>
  );
}
