"use client";

// Iconos de interfaz de Phosphor, peso "light", importados uno por uno (sin el barril, que
// arrastraría los +1500 iconos). Para dibujos del dominio usar <Icon> (iconos propios).
import type { IconProps } from "@phosphor-icons/react/dist/lib/types";
import { ArrowClockwiseIcon } from "@phosphor-icons/react/dist/csr/ArrowClockwise";
import { CameraIcon } from "@phosphor-icons/react/dist/csr/Camera";
import { CheckIcon } from "@phosphor-icons/react/dist/csr/Check";
import { ClipboardTextIcon } from "@phosphor-icons/react/dist/csr/ClipboardText";
import { DownloadSimpleIcon } from "@phosphor-icons/react/dist/csr/DownloadSimple";
import { MapPinIcon } from "@phosphor-icons/react/dist/csr/MapPin";
import { MapTrifoldIcon } from "@phosphor-icons/react/dist/csr/MapTrifold";
import { MegaphoneIcon } from "@phosphor-icons/react/dist/csr/Megaphone";
import { SignOutIcon } from "@phosphor-icons/react/dist/csr/SignOut";
import { StackIcon } from "@phosphor-icons/react/dist/csr/Stack";
import { TrophyIcon } from "@phosphor-icons/react/dist/csr/Trophy";
import { UserIcon } from "@phosphor-icons/react/dist/csr/User";
import { WarningIcon } from "@phosphor-icons/react/dist/csr/Warning";
import { XIcon } from "@phosphor-icons/react/dist/csr/X";
import type { ComponentType } from "react";

const UI_ICONS = {
  mapa: MapTrifoldIcon,
  reportar: MegaphoneIcon,
  inspecciones: ClipboardTextIcon,
  ranking: TrophyIcon,
  perfil: UserIcon,
  salir: SignOutIcon,
  cerrar: XIcon,
  reintentar: ArrowClockwiseIcon,
  descargar: DownloadSimpleIcon,
  ubicacion: MapPinIcon,
  camara: CameraIcon,
  capas: StackIcon,
  listo: CheckIcon,
  aviso: WarningIcon,
} satisfies Record<string, ComponentType<IconProps>>;

export type UiIconName = keyof typeof UI_ICONS;

/** Icono de interfaz (Phosphor light). Decorativo salvo que reciba `label`. */
export function UiIcon({ name, size = 20, label }: { name: UiIconName; size?: number; label?: string }) {
  const Component = UI_ICONS[name];
  return (
    <Component
      weight="light"
      size={size}
      className="icon"
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      focusable={false}
    />
  );
}
