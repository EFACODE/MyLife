import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({
  value: { preference: { order: [] as string[], hidden: [] as string[] }, save: vi.fn() },
}));
vi.mock("../../auth/MeContext", () => ({
  useMe: () => ({ user: { user_id: "u", role: "member" }, status: "ready" }),
}));
vi.mock("../../auth/NavPreferencesContext", () => ({ useNavPreferences: () => nav.value }));

import { MenuSettingsPage } from "./MenuSettingsPage";

function labels() {
  return within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((li) => li.textContent?.replace("Mostrar", "").trim());
}

describe("MenuSettingsPage", () => {
  beforeEach(() => {
    nav.value = { preference: { order: [], hidden: [] }, save: vi.fn().mockResolvedValue(undefined) };
  });

  it("lists the items in the saved order", () => {
    nav.value.preference = { order: ["/goals"], hidden: [] };
    render(<MenuSettingsPage />);
    expect(labels()[0]).toBe("Metas");
    expect(labels()).not.toContain("Usuários e grupos"); // admin-only
  });

  it("moves an item and hides another, then saves the full order", async () => {
    render(<MenuSettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Mover Saúde para cima" }));
    expect(labels().slice(0, 2)).toEqual(["Saúde", "Finanças"]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Mostrar Metas" }));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(nav.value.save).toHaveBeenCalled());
    const saved = nav.value.save.mock.calls[0][0];
    expect(saved.order.slice(0, 2)).toEqual(["/health", "/finance"]);
    expect(saved.hidden).toEqual(["/goals"]);
    expect(await screen.findByRole("status")).toHaveTextContent("Menu atualizado.");
  });

  it("keeps at least one item visible", () => {
    render(<MenuSettingsPage />);
    const boxes = screen.getAllByRole("checkbox");
    boxes.slice(1).forEach((box) => fireEvent.click(box));
    expect(boxes[0]).toBeChecked();
    expect(boxes[0]).toBeDisabled();
    expect(screen.getByText("Pelo menos um item precisa ficar visível.")).toBeInTheDocument();
  });

  it("restores the default order with nothing hidden", () => {
    nav.value.preference = { order: ["/goals"], hidden: ["/finance"] };
    render(<MenuSettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Restaurar padrão" }));
    expect(labels()[0]).toBe("Finanças");
    expect(screen.getByRole("checkbox", { name: "Mostrar Finanças" })).toBeChecked();
  });

  it("shows an error when saving fails", async () => {
    nav.value.save = vi.fn().mockRejectedValue(new Error("boom"));
    render(<MenuSettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível salvar o menu.");
  });
});
