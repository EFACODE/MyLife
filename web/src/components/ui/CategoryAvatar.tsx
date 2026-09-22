import { categorySolidClass } from "../../lib/categoryColor";

/** A small colored initial-circle, tinted to match the category's badge. */
export function CategoryAvatar({ label, category }: { label: string; category: string | null }) {
  const initial = (label.trim()[0] ?? "?").toUpperCase();
  const fill = category ? categorySolidClass(category) : "bg-gray-400";
  return (
    <span
      className={
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white " +
        fill
      }
      aria-hidden="true"
    >
      {initial}
    </span>
  );
}
