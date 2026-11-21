"use client";

import { useId, useState } from "react";
import { useMe } from "@/features/auth/api/useMe";
import { formatDate, formatNumber } from "@/features/map/labels";
import { useDebouncedValue } from "@/features/map/hooks/useDebouncedValue";
import type { ManagedUser, Role } from "@/shared/api/types";
import { ALL_ROLES, ROLE_LABELS } from "@/shared/auth/access";
import { ConfirmDialog } from "@/shared/ui/ConfirmDialog";
import { SelectField, TextField } from "@/shared/ui/fields";
import { UiIcon } from "@/shared/ui/icons/ui";
import { stagger } from "@/shared/ui/motion";
import { EmptyState, ErrorState, Skeleton } from "@/shared/ui/states";
import { USERS_PAGE_SIZE, useAdminUsers, useChangeUserRole } from "../api/queries";

const SEARCH_DEBOUNCE_MS = 300;
const usersCount = new Intl.PluralRules("es-CO");

function countLabel(total: number): string {
  return `${formatNumber(total)} ${usersCount.select(total) === "one" ? "usuario" : "usuarios"}`;
}

/** Qué implica el cambio, para decidir con conocimiento antes de confirmar. */
function consequence(from: Role, to: Role): string {
  if (to === "ADMIN") return "Tendrá control total de Vigía, incluida la gestión de usuarios y roles.";
  if (from === "ADMIN") return "Perderá el acceso a la administración y a la gestión de usuarios.";
  return "Sus permisos cambian desde su próxima acción en la app.";
}

function Flag({ value }: { value: boolean }) {
  return value ? (
    <span className="label-with-icon">
      <UiIcon name="listo" size={16} /> Sí
    </span>
  ) : (
    <span className="muted">No</span>
  );
}

interface PendingChange {
  user: ManagedUser;
  role: Role;
}

function UserRow({
  user,
  index,
  isSelf,
  selfNoteId,
  onPick,
}: {
  user: ManagedUser;
  index: number;
  isSelf: boolean;
  selfNoteId: string;
  onPick: (change: PendingChange) => void;
}) {
  return (
    <tr style={stagger(index)}>
      <th scope="row" data-label="Nombre">
        <span className="users-name">{user.name}</span>
        {isSelf && <span className="muted"> (tú)</span>}
      </th>
      <td data-label="Rol">
        <select
          className="users-role"
          aria-label={`Rol de ${user.name}`}
          aria-describedby={isSelf ? selfNoteId : undefined}
          value={user.role}
          disabled={isSelf}
          onChange={(event) => onPick({ user, role: event.target.value as Role })}
        >
          {ALL_ROLES.map((role) => (
            <option key={role} value={role}>
              {ROLE_LABELS[role]}
            </option>
          ))}
        </select>
      </td>
      <td data-label="Puntos" className="numeric mono">
        {formatNumber(user.points)}
      </td>
      <td data-label="Alta">
        <time dateTime={user.created_at}>{formatDate(user.created_at)}</time>
      </td>
      <td data-label="Ubicación">
        <Flag value={user.has_location} />
      </td>
      <td data-label="Telegram">
        <Flag value={user.telegram_linked} />
      </td>
    </tr>
  );
}

/** Gestión de usuarios (solo ADMIN): búsqueda, filtro por rol, paginación y cambio de rol. */
export function UsersAdmin() {
  const me = useMe();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<Role | null>(null);
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const selfNoteId = useId();

  const debouncedSearch = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const users = useAdminUsers({ search: debouncedSearch, role, page });
  const changeRole = useChangeUserRole();

  const hasFilters = search.trim() !== "" || role !== null;
  const clearFilters = () => {
    setSearch("");
    setRole(null);
    setPage(1);
  };

  const pick = (change: PendingChange) => {
    changeRole.reset();
    setPending(change);
  };

  const confirm = () => {
    if (!pending) return;
    const { user, role: next } = pending;
    changeRole.mutate(
      { userId: user.id, role: next },
      {
        onSuccess: (updated) => {
          setPending(null);
          setAnnouncement(`Rol de ${updated.name} cambiado a ${ROLE_LABELS[updated.role]}.`);
        },
      },
    );
  };

  const data = users.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / USERS_PAGE_SIZE)) : 1;

  let content;
  if (users.isPending) {
    content = <Skeleton label="Cargando usuarios…" variant="list" lines={6} />;
  } else if (!data) {
    content = <ErrorState message={users.error?.message ?? "No se pudieron cargar los usuarios."} onRetry={() => users.refetch()} />;
  } else if (data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState
        icon="geocerca"
        title="Ningún usuario coincide"
        action={
          <button type="button" onClick={clearFilters}>
            Quitar filtros
          </button>
        }
      >
        <p>Prueba con otra parte del nombre o con otro rol.</p>
      </EmptyState>
    ) : (
      <EmptyState icon="geocerca" title="Aún no hay usuarios">
        <p>Las cuentas aparecen aquí cuando alguien se registra e inicia sesión.</p>
      </EmptyState>
    );
  } else {
    content = (
      <>
        {users.isError && (
          <ErrorState message={users.error.message} onRetry={() => users.refetch()} />
        )}
        <div className="users-table-wrap">
          <table className="users-table" aria-busy={users.isFetching}>
            <caption className="visually-hidden">
              Usuarios de Vigía, página {page} de {totalPages}
            </caption>
            <thead>
              <tr>
                <th scope="col">Nombre</th>
                <th scope="col">Rol</th>
                <th scope="col" className="numeric">
                  Puntos
                </th>
                <th scope="col">Alta</th>
                <th scope="col">Ubicación</th>
                <th scope="col">Telegram</th>
              </tr>
            </thead>
            <tbody className="stagger">
              {data.items.map((user, index) => (
                <UserRow
                  key={user.id}
                  user={user}
                  index={index}
                  isSelf={user.id === me.data?.id}
                  selfNoteId={selfNoteId}
                  onPick={pick}
                />
              ))}
            </tbody>
          </table>
        </div>
        {data.items.some((u) => u.id === me.data?.id) && (
          <p id={selfNoteId} className="muted">
            Tu propio rol no se puede cambiar desde aquí; otro administrador debe hacerlo.
          </p>
        )}
        {totalPages > 1 && (
          <nav className="pager" aria-label="Paginación de usuarios">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <UiIcon name="anterior" size={18} /> Anterior
            </button>
            <span className="mono">
              Página {page} de {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Siguiente <UiIcon name="siguiente" size={18} />
            </button>
          </nav>
        )}
      </>
    );
  }

  return (
    <>
      <form className="users-filters" role="search" onSubmit={(event) => event.preventDefault()}>
        <TextField
          label="Buscar por nombre"
          type="search"
          name="q"
          autoComplete="off"
          spellCheck={false}
          maxLength={200}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
        <SelectField
          label="Rol"
          name="rol"
          value={role ?? ""}
          onChange={(event) => {
            setRole((event.target.value || null) as Role | null);
            setPage(1);
          }}
        >
          <option value="">Todos los roles</option>
          {ALL_ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </SelectField>
      </form>

      <p className="users-count" role="status">
        {data ? countLabel(data.total) : ""}
        {announcement && <span className="users-announcement"> · {announcement}</span>}
      </p>

      {content}

      <ConfirmDialog
        open={pending !== null}
        title="Cambiar rol"
        confirmLabel={changeRole.isPending ? "Cambiando…" : "Cambiar rol"}
        busy={changeRole.isPending}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      >
        {pending && (
          <>
            <p>
              ¿Cambiar el rol de <strong>{pending.user.name}</strong> de{" "}
              {ROLE_LABELS[pending.user.role]} a <strong>{ROLE_LABELS[pending.role]}</strong>?
            </p>
            <p className="muted">{consequence(pending.user.role, pending.role)}</p>
            {changeRole.isError && (
              <p className="error" role="alert">
                {changeRole.error.message}
              </p>
            )}
          </>
        )}
      </ConfirmDialog>
    </>
  );
}
