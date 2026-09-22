import { categoryBadgeClasses } from "../../lib/categoryColor";

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) {
    return <span className="text-xs text-gray-400">Sem categoria</span>;
  }
  return (
    <span
      className={
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium " +
        categoryBadgeClasses(category)
      }
    >
      {category}
    </span>
  );
}
