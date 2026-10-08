import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { Layout } from "./Layout";

const USER = {
  user_id: "u",
  email: "a@b.c",
  display_name: "Ada",
  status: "active",
  household_id: null,
  created_at: "2026-01-01T00:00:00Z",
};

describe("Layout", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("mylife.token", "t");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => USER }),
    );
  });

  function renderLayout(path = "/") {
    return render(
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<div>dashboard content</div>} />
              <Route path="/finance" element={<div>finance content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );
  }

  it("renders the sidebar nav, logout, and the routed page", async () => {
    renderLayout();
    expect(screen.getByRole("link", { name: "Painel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sair" })).toBeInTheDocument();
    expect(await screen.findByText("dashboard content")).toBeInTheDocument();
  });

  it("lists Painel last and no longer has a separate Registrar entry", () => {
    renderLayout();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    const labels = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(labels[labels.length - 2]).toBe("Privacidade");
    expect(labels[labels.length - 1]).toBe("Painel");
    expect(labels).not.toContain("Registrar");
  });

  it("shows the current page title in the mobile top bar", async () => {
    renderLayout("/finance");
    expect(await screen.findByText("finance content")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Finanças");
  });

  it("opens the mobile drawer and closes it on navigation", async () => {
    renderLayout();
    const toggle = screen.getByRole("button", { name: "Abrir menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.click(screen.getByRole("link", { name: "Finanças" }));
    expect(await screen.findByText("finance content")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.body.style.overflow).toBe("");
  });

  it("closes the mobile drawer with Escape and the close button", () => {
    renderLayout();
    const toggle = screen.getByRole("button", { name: "Abrir menu" });

    fireEvent.click(toggle);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "Fechar menu" }));
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
