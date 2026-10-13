import { ArrowDown, ArrowUp, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";

import { useMe } from "../../auth/MeContext";
import { useNavPreferences } from "../../auth/NavPreferencesContext";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Section } from "../../components/ui/Section";
import { navFor, resolveNav, type ResolvedNavItem } from "../../nav";

/**
 * "Personalizar menu" (T10.12): reorder the sidebar items and hide the ones the
 * user doesn't need. Hiding only removes an item from the menu — its page still
 * opens from links/URLs. At least one item always stays visible.
 */
export function MenuSettingsPage() {
  const { user } = useMe();
  const { preference, save } = useNavPreferences();
  const available = navFor(user?.role);
  const [draft, setDraft] = useState<ResolvedNavItem[] | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  // Start editing from the saved preference once it (and the user's role) is known.
  const loaded = user !== null;
  const role = user?.role;
  useEffect(() => {
    if (preference && loaded) setDraft(resolveNav(navFor(role), preference));
  }, [preference, loaded, role]);

  if (!draft) return <p className="text-sm text-gray-500">Carregando…</p>;

  const visibleCount = draft.filter((entry) => !entry.hidden).length;

  function update(next: ResolvedNavItem[]) {
    setDraft(next);
    setStatus("idle");
  }

  function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (!draft || target < 0 || target >= draft.length) return;
    const next = [...draft];
    [next[index], next[target]] = [next[target], next[index]];
    update(next);
  }

  function toggle(index: number) {
    if (!draft) return;
    update(draft.map((entry, i) => (i === index ? { ...entry, hidden: !entry.hidden } : entry)));
  }

  async function submit() {
    if (!draft) return;
    setStatus("saving");
    try {
      await save({
        order: draft.map((entry) => entry.item.path),
        hidden: draft.filter((entry) => entry.hidden).map((entry) => entry.item.path),
      });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div>
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">Personalizar menu</h1>
      <p className="mb-6 text-sm text-gray-500">
        Reordene os itens do menu lateral e oculte os que você não usa. Itens ocultos continuam
        acessíveis pelos links do app — só saem do menu.
      </p>
      <Section title="Itens do menu" icon={SlidersHorizontal}>
        <ol className="mb-4 flex flex-col gap-2">
          {draft.map((entry, index) => {
            const Icon = entry.item.icon;
            const isLastVisible = !entry.hidden && visibleCount === 1;
            return (
              <li
                key={entry.item.path}
                className={
                  "flex items-center gap-3 rounded border px-3 py-2 text-sm " +
                  (entry.hidden ? "border-dashed border-gray-300 bg-gray-50 text-gray-400" : "border-gray-200")
                }
              >
                <Icon className="h-5 w-5 shrink-0 md:h-4 md:w-4" aria-hidden />
                <span className="min-w-0 flex-1 truncate font-medium">{entry.item.label}</span>
                <label className="flex min-h-11 items-center gap-2 sm:min-h-0">
                  <input
                    type="checkbox"
                    checked={!entry.hidden}
                    disabled={isLastVisible}
                    onChange={() => toggle(index)}
                    aria-label={`Mostrar ${entry.item.label}`}
                    className="h-4 w-4"
                  />
                  <span className="hidden text-gray-600 sm:inline">Mostrar</span>
                </label>
                <span className="flex">
                  <button
                    type="button"
                    onClick={() => move(index, -1)}
                    disabled={index === 0}
                    aria-label={`Mover ${entry.item.label} para cima`}
                    className="flex h-11 w-11 items-center justify-center rounded text-gray-600 hover:bg-gray-100 disabled:opacity-30 sm:h-8 sm:w-8"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(index, 1)}
                    disabled={index === draft.length - 1}
                    aria-label={`Mover ${entry.item.label} para baixo`}
                    className="flex h-11 w-11 items-center justify-center rounded text-gray-600 hover:bg-gray-100 disabled:opacity-30 sm:h-8 sm:w-8"
                  >
                    <ArrowDown className="h-4 w-4" />
                  </button>
                </span>
              </li>
            );
          })}
        </ol>
        {visibleCount === 1 && (
          <p className="mb-3 text-xs text-gray-500">Pelo menos um item precisa ficar visível.</p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={submit} disabled={status === "saving"}>
            Salvar
          </Button>
          <button
            type="button"
            onClick={() => update(resolveNav(available, null))}
            className="text-sm text-blue-600 hover:underline"
          >
            Restaurar padrão
          </button>
          {status === "saved" && (
            <span role="status" className="text-sm text-green-700">
              Menu atualizado.
            </span>
          )}
        </div>
        {status === "error" && (
          <div className="mt-3">
            <ErrorText>Não foi possível salvar o menu.</ErrorText>
          </div>
        )}
      </Section>
    </div>
  );
}
