export interface TabItem {
  id: string;
  label: string;
}

export function Tabs({
  items,
  active,
  onChange,
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div role="tablist" className="no-scrollbar -mx-4 mb-6 flex gap-1 overflow-x-auto border-b border-gray-200 px-4 sm:mx-0 sm:px-0">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          onClick={(e) => {
              onChange(item.id);
              // Keep the chosen tab fully visible when the strip scrolls sideways on phones.
              e.currentTarget.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
            }}
          className={
            "shrink-0 whitespace-nowrap border-b-2 px-3 py-3 text-sm font-medium sm:py-2 " +
            (active === item.id
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-gray-500 hover:text-gray-700")
          }
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
