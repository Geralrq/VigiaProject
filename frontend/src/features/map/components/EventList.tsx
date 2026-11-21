import type { Selection } from "../selection";
import { EmptyState } from "@/shared/ui/states";
import type { IconName } from "@/shared/ui/icons/paths";
import { Icon } from "@/shared/ui/icons/Icon";

export interface EventItem extends Selection {
  label: string;
  icon: IconName;
}

interface Props {
  items: EventItem[];
  selected: Selection | null;
  onSelect: (item: Selection) => void;
}

const MAX_ITEMS = 25;

/** Alternativa por teclado a hacer clic en el mapa: cada evento visible es un botón. */
export function EventList({ items, selected, onSelect }: Props) {
  return (
    <section aria-label="Eventos en el área visible">
      <h3>Eventos visibles</h3>
      {items.length === 0 ? (
        <EmptyState icon="satelite" title="Nada que revisar aquí">
          <p>No hay anomalías ni alertas en el área visible. Aleja el mapa o activa más capas.</p>
        </EmptyState>
      ) : (
        <ul>
          {items.slice(0, MAX_ITEMS).map((item) => {
            const isSelected = selected?.kind === item.kind && selected.id === item.id;
            return (
              <li key={`${item.kind}-${item.id}`}>
                <button
                  type="button"
                  onClick={() => onSelect({ kind: item.kind, id: item.id })}
                  aria-pressed={isSelected}
                >
                  <Icon name={item.icon} size={18} />
                  <span>{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {items.length > MAX_ITEMS && (
        <p className="muted">Mostrando {MAX_ITEMS} de {items.length}. Acerca el mapa para ver más.</p>
      )}
    </section>
  );
}
