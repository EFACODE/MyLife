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
      className="no-scrollbar mb-6 flex max-w-full gap-1 overflow-x-auto rounded-xl bg-gray-100 p-1 sm:inline-flex sm:flex-wrap"
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
            onClick={(e) => {
              onChange(item.id);
              // Keep the chosen tab fully visible when the strip scrolls sideways on phones.
              e.currentTarget.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
            }}
            className={
              "flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors sm:py-1.5 " +
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
