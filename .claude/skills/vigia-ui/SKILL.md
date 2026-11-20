---
name: vigia-ui
description: Reglas de identidad visual de Vigía ("centro de comando ambiental", oscuro). Úsala SIEMPRE que se cree o cambie cualquier vista, componente, estilo, color, tipografía o mapa del frontend (frontend/src), también si el pedido parece solo funcional pero toca algo visible.
---

# Vigía UI — «Centro de comando» (dirección A, toda la app)

Sala de situación oscura, mapa protagonista. **El color solo significa riesgo.** Lo demás es verde-tinta y hielo neutro: si algo se ve naranja o rojo, es una alerta real.

## Tokens (única fuente: `src/shared/styles/tokens.css`)
- Ningún `.css`/`.tsx` lleva colores, medidas ni fuentes literales: solo `var(--token)`. MapLibre/deck.gl leen tokens con `readToken()` (`shared/styles/tokens.ts`).
- Superficies: `--color-bg` (lienzo) < `--color-surface` < `--color-surface-raised`. Texto `--color-text`; secundario `--color-text-muted`.
- Hielo `--color-accent` = acción primaria, foco y selección (texto encima: `--color-on-accent`). Es el único acento.
- Riesgo: `--risk-bajo|medio|alto|critico`; texto sobre relleno de riesgo `--risk-on-fill`. Todo AA (≥4,5:1 texto, ≥3:1 controles).
- Bordes: `--color-border` solo decorativo (líneas de 1 px); controles interactivos usan `--color-border-control` (≥3:1).
- Si falta un valor, **se añade el token** a tokens.css con su contraste verificado; no se escribe en el componente.

## Riesgo nunca solo con color
Usa `<RiskBadge level>` (features/map): glifo de 1–4 barras + etiqueta en texto (Bajo, Medio, Alto, Crítico). ALTO y CRÍTICO se parecen en color; el glifo y el texto los distinguen. Excepciones en el mapa, sin significar riesgo: incendio = naranja de fuego, deforestación = arena (suelo desnudo).

## Tipografía
- Archivo variable: títulos en semi-expandida (`--font-display`, `font-stretch: var(--width-display)`), cuerpo en normal (`--font-body`).
- IBM Plex Mono (`--font-mono`) solo para coordenadas, fechas y cifras de instrumento; cifras con `font-variant-numeric: tabular-nums`.
- Escala `--text-xs|sm|md|lg|xl` (12/14/16/20/28). Texto de UI en español, frases en minúscula (sentence case), sin MAYÚSCULAS sostenidas ni «→» decorativos.

## Paneles y forma
- Rieles acoplados a los bordes (izquierdo: capas y eventos; derecho: detalle). Sin vidrio, sin difuminados, sin sombras; radio único `--radius` (2 px); separadores de 1 px.
- Nada de tarjetas idénticas: jerarquía por tipografía, filetes y listas de definición (`dl.facts`). El detalle lleva un filo izquierdo del color de su riesgo (`data-risk`).
- Una sola animación de entrada (panel de detalle, `--motion-panel`); lo demás cambia sin transición. `prefers-reduced-motion` la anula.

## Mapa
- Base: teselas raster OSM invertidas a oscuro con los tokens `--map-base-*` (sin proveedor ni token de pago; para producción cambiar de proveedor, el filtro sirve igual).
- Zonas: línea fina hielo + relleno tenue. Anomalías: relleno por tipo, opacidad por confianza. Alertas: línea punteada y relleno en el color de su `risk_level`. Focos FIRMS: heatmap ámbar→rojo. Selección: contorno `--color-text` de 4 px.
- Controles de MapLibre se re-tematizan en base.css; nada de colores por defecto de la librería.

## Accesibilidad (mínimos no negociables)
- Foco siempre visible (`:focus-visible`, anillo `--focus-ring-width` en `--color-focus`); jamás `outline: none` sin reemplazo.
- Objetivos táctiles ≥ `--touch-target` (44 px). Navegación por teclado completa: todo lo que se hace con clic en el mapa tiene alternativa en una lista de botones.
- Etiquetas visibles en formularios; errores junto al campo con `role="alert"`; estados de carga con `aria-busy`/`role="status"`.
- Responsive: ≥ 52 rem tres columnas (rieles + mapa); por debajo, el mapa arriba y los paneles apilados debajo. Sin scroll horizontal.

## Al construir una vista nueva
1. Lee esta skill y tokens.css; reutiliza `.panel`, `.facts`, `.risk-badge`, botones base.
2. Estructura semántica primero (landmarks, encabezados), estilo después con tokens.
3. Prohibido: gradientes morados/genéricos, cuadrículas de tarjetas iguales, acentos de color decorativos, emojis como iconos.
4. Antes de terminar: lint, tipos, build y revisión de contraste de cualquier color nuevo.
