import { render, screen } from "@testing-library/react";
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

  it("renders the sidebar nav, logout, and the routed page", async () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<div>dashboard content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );
    expect(screen.getByText("Painel")).toBeInTheDocument();
    expect(screen.getByText("Sair")).toBeInTheDocument();
    expect(await screen.findByText("dashboard content")).toBeInTheDocument();
  });
});
