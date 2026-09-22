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
    <div role="tablist" className="mb-6 flex gap-1 border-b border-gray-200">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          onClick={() => onChange(item.id)}
          className={
            "border-b-2 px-3 py-2 text-sm font-medium " +
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
