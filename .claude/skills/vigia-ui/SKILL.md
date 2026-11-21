---
name: vigia-ui
description: Reglas de identidad visual de Vigía ("centro de comando ambiental", oscuro). Úsala SIEMPRE que se cree o cambie cualquier vista, componente, estilo, color, tipografía, icono, animación o mapa del frontend (frontend/src), también si el pedido parece solo funcional pero toca algo visible.
---

# Vigía UI — «Centro de comando» (dirección A, toda la app)

Sala de situación oscura, mapa protagonista. **El color solo significa riesgo.** Lo demás es verde-tinta y hielo neutro: si algo se ve naranja o rojo, es una alerta real.

## Tokens (única fuente: `src/shared/styles/tokens.css`)
- Ningún `.css`/`.tsx` lleva colores, medidas, fuentes ni duraciones literales: solo `var(--token)`. MapLibre/deck.gl leen tokens con `readToken()`. Excepción documentada: manifest y `themeColor` (no leen CSS).
- Superficies `--color-bg` < `--color-surface` < `--color-surface-raised`; texto `--color-text` / `--color-text-muted`. Hielo `--color-accent` = acción primaria, foco y selección (único acento).
- Riesgo `--risk-bajo|medio|alto|critico` (AA ≥4,5:1); bordes de control `--color-border-control` (≥3:1); `--color-border` solo decorativo.
- Si falta un valor, **se añade el token** con su contraste verificado; nunca en el componente.

## Iconos
- Dominio (incendio, deforestación, inundación, satélite, foco, geocerca, misión, informe, marcadores): `<Icon name>` de `shared/ui/icons` (trazo 1,5, `currentColor`). Los trazados viven en `paths.ts` y son la única fuente: `markerSvg()` hace los marcadores de MapLibre y `logoSvg()` el favicon y los iconos del manifest.
- Interfaz (cerrar, reintentar, descargar, menú…): `<UiIcon name>` = Phosphor `light`, importado **icono por icono** desde `@phosphor-icons/react/dist/csr/<Nombre>`; nunca el barril, Lucide ni Heroicons. Icono nuevo = añadirlo al mapa de `ui.tsx`.
- Iconos decorativos con `aria-hidden`; botón solo-icono con `aria-label` y `.icon-button`. Nada de emojis.
- Riesgo: `<RiskBadge level>` = `RiskGlyph` (1–4 barras) + texto. ALTO y CRÍTICO se distinguen por glifo y texto, no solo por color.

## Tipografía
- Archivo variable: títulos y cifras grandes en semi-expandida (`--font-display`, `--width-display`); cuerpo normal. Plex Mono solo para coordenadas y fechas.
- Escala 12/14/16/20/28 (`--text-xs…xl`). Números comparables con `tabular-nums`. Sentence case, sin MAYÚSCULAS sostenidas.

## Paneles y estados
- Rieles acoplados, sin vidrio ni sombras; radio único `--radius`. Jerarquía con tipografía, filetes y `dl.facts`; listas `.entry-list`, nunca tarjetas idénticas.
- Carga = `<Skeleton>`; vacío = `<EmptyState icon title action>` (ilustración + qué hacer); error = `<ErrorState message onRetry>`. Nunca un «Cargando…» suelto.
- Formularios: `TextField`/`SelectField`/`ChoiceGroup`/`PhotoField`; acciones con efectos sobre otras personas, con `ConfirmDialog`.

## Movimiento
- Solo CSS y APIs del navegador (sin librerías). Animar **solo transform y opacity**; `transition-property` explícito (nunca `all`). Duraciones `--motion-fast|base|panel|ambient`, curvas `--ease-out|in-out`.
- Todo respeta `prefers-reduced-motion`: CSS global en base.css + bloque final de motion.css; en JS usar `prefersReducedMotion()`/`useReducedMotion()` (`shared/ui/motion.ts`). Con movimiento reducido el contenido final aparece igual.
- Repertorio: listas con `.stagger` + `style={stagger(i)}`; cifras con `<CountUp>` (el lector oye el valor final); cambios de selección/pestaña con `withViewTransition()`; mapa con `flyTo` y pulso de alertas por riesgo; radar en «Escanear ahora»; barra de tiempo en avisos (pausa en hover/foco). Un movimiento por intención; nada en bucle salvo esperas y el fondo del login.

## Mapa
- Base OSM invertida con `--map-base-*`. Marcadores con icono en el centro de cada anomalía, alerta (flota encima, color de riesgo) y reporte; los polígonos siguen debajo.
- Leyenda (`MapLegend`), escala y atribución siempre visibles. Estado compartible en la URL: `?capas=…&sel=anomalia:<id>` (`features/map/url-state.ts`, `router.replace`).
- Móvil (< 52 rem): mapa completo + `<BottomSheet>` (Capas, Detalle, Impacto), arrastrable y operable con teclado.

## Accesibilidad (no negociable)
- Foco visible siempre; objetivos ≥ `--touch-target`; todo lo del mapa tiene alternativa en lista de botones; etiquetas visibles; `role="status"`/`aria-busy` en esperas; patrón ARIA correcto en pestañas y diálogos.

## Al construir una vista nueva
1. Lee esta skill y tokens.css; reutiliza `shared/ui` (iconos, estados, campos, diálogo, motion).
2. Prohibido: gradientes morados o decorativos, tarjetas iguales, acentos de color sin significado, emojis, dependencias de animación.
3. Antes de terminar: lint, tipos, build, contraste de colores nuevos y prueba con movimiento reducido.
