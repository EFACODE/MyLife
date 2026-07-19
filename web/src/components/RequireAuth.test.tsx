import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { RequireAuth } from "./RequireAuth";

function renderAt(path: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>home</div>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => localStorage.clear());

  it("redirects to /login when unauthenticated", () => {
    renderAt("/");
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    localStorage.setItem("mylife.token", "t");
    renderAt("/");
    expect(screen.getByText("home")).toBeInTheDocument();
  });
});
