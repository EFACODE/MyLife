import type { ComponentType, ReactNode } from "react";

export function Section({
  title,
  icon: Icon,
  actions,
  children,
}: {
  title: string;
  icon?: ComponentType<{ className?: string }>;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
          {Icon && (
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
              <Icon className="h-4 w-4" />
            </span>
          )}
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
