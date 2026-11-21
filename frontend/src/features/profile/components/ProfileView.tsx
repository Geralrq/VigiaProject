"use client";

import { useState, type FormEvent } from "react";
import { useMe } from "@/features/auth/api/useMe";
import { validateName } from "@/features/auth/validation";
import { formatNumber } from "@/features/map/labels";
import { ROLE_LABELS } from "@/shared/auth/access";
import { useGeolocation } from "@/shared/hooks/useGeolocation";
import { TextField } from "@/shared/ui/fields";
import { useSetTelegramChat, useTelegramLink, useUpdateProfile } from "../api/queries";

// El campo de chat_id manual solo existe en demo (el backend también lo rechaza en live).
const DEMO_MODE = process.env.NEXT_PUBLIC_APP_MODE === "demo";

const timeFormat = new Intl.DateTimeFormat("es-CO", { timeStyle: "short" });

function NameForm({ initialName }: { initialName: string }) {
  const update = useUpdateProfile();
  const [name, setName] = useState(initialName);
  const [error, setError] = useState<string | undefined>();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateName(name) ?? undefined;
    setError(invalid);
    if (!invalid) update.mutate({ name: name.trim() });
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Tu nombre">
      <TextField
        label="Nombre"
        name="name"
        autoComplete="name"
        value={name}
        error={error}
        onChange={(e) => {
          setName(e.target.value);
          update.reset();
        }}
      />
      {update.isSuccess && <p role="status">Nombre guardado.</p>}
      {update.isError && (
        <p role="alert" className="error">
          {update.error.message}
        </p>
      )}
      <button type="submit" disabled={update.isPending} aria-busy={update.isPending}>
        {update.isPending ? "Guardando…" : "Guardar nombre"}
      </button>
    </form>
  );
}

function LocationSection({ location }: { location: [number, number] | null }) {
  const update = useUpdateProfile();
  const geo = useGeolocation();

  return (
    <section aria-labelledby="location-title">
      <h2 id="location-title">Ubicación</h2>
      <p>
        {location ? (
          <>
            Guardada: <span className="mono">{location[1].toFixed(4)}, {location[0].toFixed(4)}</span>
          </>
        ) : (
          "Todavía no tienes una ubicación guardada."
        )}
      </p>
      <p className="muted">
        La usamos para avisarte de anomalías cercanas y asignarte misiones de verificación. Nadie
        más la ve.
      </p>
      {geo.message && (
        <p role="alert" className="error">
          {geo.message}
        </p>
      )}
      {update.isError && (
        <p role="alert" className="error">
          {update.error.message}
        </p>
      )}
      {update.isSuccess && <p role="status">Ubicación actualizada.</p>}
      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={geo.loading || update.isPending}
          aria-busy={geo.loading || update.isPending}
          onClick={() =>
            geo.request((position) => update.mutate({ location: { lat: position.lat, lng: position.lng } }))
          }
        >
          {geo.loading ? "Buscando ubicación…" : "Usar mi ubicación actual"}
        </button>
        {location && (
          <button
            type="button"
            disabled={update.isPending}
            onClick={() => update.mutate({ location: null })}
          >
            Quitar mi ubicación
          </button>
        )}
      </div>
    </section>
  );
}

function TelegramSection({ linked, onRefresh }: { linked: boolean; onRefresh: () => void }) {
  const link = useTelegramLink();
  const setChat = useSetTelegramChat();
  const [chatId, setChatId] = useState("");
  const [chatError, setChatError] = useState<string | undefined>();

  function onSubmitChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(chatId.trim());
    if (!chatId.trim() || !Number.isSafeInteger(value) || value === 0) {
      setChatError("Escribe el número del chat (solo dígitos, puede empezar con -).");
      return;
    }
    setChatError(undefined);
    setChat.mutate(value);
  }

  return (
    <section aria-labelledby="telegram-title">
      <h2 id="telegram-title">Telegram</h2>
      <p>
        {linked
          ? "Tu cuenta está vinculada: recibirás las alertas por Telegram."
          : "Vincula Telegram para recibir alertas en tu celular."}
      </p>
      <div className="actions">
        <button
          type="button"
          onClick={() => link.mutate()}
          disabled={link.isPending}
          aria-busy={link.isPending}
        >
          {link.isPending ? "Generando enlace…" : linked ? "Vincular de nuevo" : "Vincular Telegram"}
        </button>
        <button type="button" onClick={onRefresh}>
          Actualizar estado
        </button>
      </div>
      {link.isError && (
        <p role="alert" className="error">
          {link.error.message}
        </p>
      )}
      {link.data && (
        <div role="status">
          {link.data.deep_link ? (
            <p>
              <a className="button" href={link.data.deep_link} target="_blank" rel="noopener noreferrer">
                Abrir Telegram y vincular
              </a>
            </p>
          ) : (
            <p>
              Envía este mensaje al bot de Vigía: <span className="mono">{link.data.command}</span>
            </p>
          )}
          <p className="muted">
            El enlace vence a las{" "}
            <time dateTime={link.data.expires_at}>{timeFormat.format(new Date(link.data.expires_at))}</time>. Al
            terminar, toca «Actualizar estado».
          </p>
        </div>
      )}

      {DEMO_MODE && (
        <form onSubmit={onSubmitChat} noValidate aria-label="Fijar chat de Telegram (demo)">
          <TextField
            label="Chat de Telegram (solo modo demo)"
            name="chat_id"
            inputMode="numeric"
            autoComplete="off"
            hint="Fija el chat_id a mano para probar las alertas sin pasar por el bot."
            value={chatId}
            error={chatError}
            onChange={(e) => setChatId(e.target.value)}
          />
          {setChat.isSuccess && <p role="status">Chat guardado.</p>}
          {setChat.isError && (
            <p role="alert" className="error">
              {setChat.error.message}
            </p>
          )}
          <button type="submit" disabled={setChat.isPending}>
            {setChat.isPending ? "Guardando…" : "Fijar chat"}
          </button>
        </form>
      )}
    </section>
  );
}

export function ProfileView() {
  const me = useMe();

  if (me.isPending) return <p role="status">Cargando tu perfil…</p>;
  if (me.isError) {
    return (
      <div role="alert">
        <p className="error">{me.error.message}</p>
        <button type="button" onClick={() => me.refetch()}>
          Reintentar
        </button>
      </div>
    );
  }

  const profile = me.data;
  return (
    <>
      <dl className="facts">
        <dt>Rol</dt>
        <dd>{ROLE_LABELS[profile.role]}</dd>
        <dt>Puntos</dt>
        <dd className="mono">{formatNumber(profile.points)}</dd>
      </dl>
      <section aria-labelledby="name-title">
        <h2 id="name-title">Nombre</h2>
        <NameForm key={profile.name} initialName={profile.name} />
      </section>
      <LocationSection location={profile.location?.coordinates ?? null} />
      <TelegramSection linked={profile.telegram_linked} onRefresh={() => me.refetch()} />
    </>
  );
}
