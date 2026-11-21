import type { IconName } from "@/shared/ui/icons/paths";
import { Icon } from "@/shared/ui/icons/Icon";
export type LayerId = "zones" | "anomalies" | "hotspots" | "alerts" | "reports";

export interface LayerOption {
  id: LayerId;
  label: string;
  icon: IconName;
}

interface Props {
  options: LayerOption[];
  active: Record<LayerId, boolean>;
  onToggle: (id: LayerId) => void;
}

export function LayerPanel({ options, active, onToggle }: Props) {
  return (
    <fieldset>
      <legend>Capas del mapa</legend>
      {options.map((option) => (
        <label key={option.id} className="layer-option">
          <input
            type="checkbox"
            checked={active[option.id]}
            onChange={() => onToggle(option.id)}
          />
          <Icon name={option.icon} size={18} />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
