import type { ComponentType } from "react";

export interface SubTabItem {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

/** A pill-style segmented control for switching between dedicated sub-screens. */
export function SubTabs({
  items,
  active,
  onChange,
}: {
  items: SubTabItem[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div
      role="tablist"
      className="mb-6 inline-flex flex-wrap gap-1 rounded-xl bg-gray-100 p-1"
    >
      {items.map((item) => {
        const Icon = item.icon;
        const isActive = active === item.id;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(item.id)}
            className={
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors " +
              (isActive
                ? "bg-white text-blue-700 shadow-sm"
                : "text-gray-600 hover:text-gray-900")
            }
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
