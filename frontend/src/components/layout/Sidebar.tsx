import clsx from "clsx";
import { BarChart3, Map } from "lucide-react";

export type DashboardView = "map" | "analytics";

interface Props {
  active: DashboardView;
  onChange: (view: DashboardView) => void;
}

const ITEMS: Array<{ id: DashboardView; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "map", label: "Risk Map", icon: Map },
  { id: "analytics", label: "Portfolio Analytics", icon: BarChart3 },
];

export function Sidebar({ active, onChange }: Props): JSX.Element {
  return (
    <nav
      aria-label="Dashboard sections"
      className="flex w-full flex-row gap-2 border-b border-slate-200 bg-white px-4 py-2 md:w-56 md:flex-col md:border-b-0 md:border-r md:px-3 md:py-4"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = item.id === active;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onChange(item.id)}
            className={clsx(
              "flex items-centre gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
              isActive
                ? "bg-brand text-white"
                : "text-slate-700 hover:bg-slate-100",
            )}
            aria-current={isActive ? "page" : undefined}
          >
            <Icon className="h-4 w-4" aria-hidden />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
