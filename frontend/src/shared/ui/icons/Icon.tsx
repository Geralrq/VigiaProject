import type { SVGProps } from "react";
import { ICONS, LOGO, type IconName, type Shape } from "./paths";

interface Props extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
  /** Nombre accesible. Sin él, el icono es decorativo (aria-hidden). */
  label?: string;
}

function Shapes({ shapes }: { shapes: readonly Shape[] }) {
  return shapes.map((shape, i) =>
    "d" in shape ? (
      <path
        key={i}
        d={shape.d}
        fill={shape.fill ? "currentColor" : "none"}
        stroke={shape.fill ? "none" : "currentColor"}
        strokeDasharray={shape.dash}
      />
    ) : (
      <circle
        key={i}
        cx={shape.cx}
        cy={shape.cy}
        r={shape.r}
        fill={shape.fill ? "currentColor" : "none"}
        stroke={shape.fill ? "none" : "currentColor"}
      />
    ),
  );
}

const BASE = {
  viewBox: "0 0 24 24",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  focusable: false,
};

/** Icono propio de Vigía (trazo fino, color = currentColor). */
export function Icon({ name, size = 20, label, className, ...rest }: Props) {
  return (
    <svg
      {...BASE}
      width={size}
      height={size}
      className={className ? `icon ${className}` : "icon"}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      {...rest}
    >
      <Shapes shapes={ICONS[name]} />
    </svg>
  );
}

/** Logotipo de Vigía. Con `label` se anuncia como imagen; si no, es decorativo. */
export function Logo({ size = 28, label }: { size?: number; label?: string }) {
  return (
    <svg
      {...BASE}
      width={size}
      height={size}
      className="icon logo"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <Shapes shapes={LOGO} />
    </svg>
  );
}

/** Glifo de nivel de riesgo (1–4 barras) en la misma familia de trazo. */
export function RiskGlyph({ bars, size = 18 }: { bars: 1 | 2 | 3 | 4; size?: number }) {
  return (
    <svg {...BASE} width={size} height={size} className="icon risk-glyph" aria-hidden>
      {[0, 1, 2, 3].map((i) => {
        const x = 4.5 + i * 4.6;
        const top = 17 - (i + 1) * 3.2;
        const on = i < bars;
        return (
          <rect
            key={i}
            x={x - 1.4}
            y={top}
            width={2.8}
            height={20 - top}
            rx={1.1}
            fill={on ? "currentColor" : "none"}
            stroke="currentColor"
            strokeOpacity={on ? 1 : 0.45}
          />
        );
      })}
    </svg>
  );
}
