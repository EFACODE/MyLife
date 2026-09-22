/**
 * Deterministic categorical color for a free-text category label (badges,
 * avatars). Eight hue families, fixed order — matching indices are picked by
 * hashing the label, never cycled based on display order, so a category keeps
 * the same color everywhere it appears (table, badges, category breakdown).
 */
const FAMILIES = [
  { bg: "bg-blue-50", text: "text-blue-700", ring: "ring-blue-600/20", solid: "bg-blue-500" },
  {
    bg: "bg-orange-50",
    text: "text-orange-700",
    ring: "ring-orange-600/20",
    solid: "bg-orange-500",
  },
  { bg: "bg-teal-50", text: "text-teal-700", ring: "ring-teal-600/20", solid: "bg-teal-500" },
  { bg: "bg-amber-50", text: "text-amber-700", ring: "ring-amber-600/20", solid: "bg-amber-500" },
  { bg: "bg-pink-50", text: "text-pink-700", ring: "ring-pink-600/20", solid: "bg-pink-500" },
  { bg: "bg-green-50", text: "text-green-700", ring: "ring-green-600/20", solid: "bg-green-600" },
  {
    bg: "bg-violet-50",
    text: "text-violet-700",
    ring: "ring-violet-600/20",
    solid: "bg-violet-500",
  },
  { bg: "bg-red-50", text: "text-red-700", ring: "ring-red-600/20", solid: "bg-red-500" },
] as const;

function hash(input: string): number {
  let hashed = 0;
  for (let i = 0; i < input.length; i++) {
    hashed = (hashed * 31 + input.charCodeAt(i)) | 0;
  }
  return Math.abs(hashed);
}

function family(category: string) {
  return FAMILIES[hash(category) % FAMILIES.length];
}

/** Badge classes: light tint background + matching ink, for a category pill. */
export function categoryBadgeClasses(category: string): string {
  const f = family(category);
  return `${f.bg} ${f.text} ring-1 ring-inset ${f.ring}`;
}

/** A solid fill for a small avatar/dot representing the category. */
export function categorySolidClass(category: string): string {
  return family(category).solid;
}
