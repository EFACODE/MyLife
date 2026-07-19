import type { ReactNode } from "react";

export function Section({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
