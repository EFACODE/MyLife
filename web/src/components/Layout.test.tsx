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

const NO_PREFS = { order: [], hidden: [], updated_at: null };

/** Answer `/users/me/nav-preferences` with `prefs` and every other call with `user`. */
function stubFetch(user: object = USER, prefs: object = NO_PREFS) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () => (url.includes("/nav-preferences") ? prefs : user),
    })),
  );
}

async function navLabels() {
  const nav = screen.getByRole("navigation", { name: "Principal" });
  await within(nav).findAllByRole("link");
  return within(nav)
    .getAllByRole("link")
    .map((link) => link.textContent);
}

describe("Layout", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("mylife.token", "t");
    stubFetch();
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
    expect(await screen.findByRole("link", { name: "Painel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sair" })).toBeInTheDocument();
    expect(await screen.findByText("dashboard content")).toBeInTheDocument();
  });

  it("lists Painel last and no longer has a separate Registrar entry", async () => {
    renderLayout();
    const labels = await navLabels();
    expect(labels[labels.length - 2]).toBe("Privacidade");
    expect(labels[labels.length - 1]).toBe("Painel");
    expect(labels).not.toContain("Registrar");
  });

  it("hides the admin console entry from non-admins", async () => {
    renderLayout();
    expect(await screen.findByText("dashboard content")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Usuários e grupos" })).not.toBeInTheDocument();
  });

  it("shows the admin console entry to admins", async () => {
    stubFetch({ ...USER, role: "admin" });
    renderLayout();
    expect(await screen.findByRole("link", { name: "Usuários e grupos" })).toBeInTheDocument();
  });

  it("applies the saved menu order and hides hidden items", async () => {
    stubFetch(USER, { order: ["/finance"], hidden: ["/health", "/goals", "/"], updated_at: "x" });
    renderLayout();
    const labels = await navLabels();
    expect(labels[0]).toBe("Finanças");
    expect(labels).not.toContain("Saúde");
    expect(labels).not.toContain("Painel");
  });

  it("always links to the menu customization from the sidebar footer", async () => {
    const everything = ["/finance", "/health", "/goals", "/knowledge", "/assistant", "/forecast",
      "/consent", "/audit", "/privacy", "/"];
    stubFetch(USER, { order: [], hidden: everything, updated_at: "x" });
    renderLayout();
    expect(await screen.findByRole("link", { name: "Personalizar menu" })).toHaveAttribute(
      "href",
      "/settings/menu",
    );
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

    fireEvent.click(await screen.findByRole("link", { name: "Finanças" }));
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
