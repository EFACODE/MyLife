import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  it("links to the signup page", () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<div>signup page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );
    expect(screen.getByText("Sign up").closest("a")).toHaveAttribute("href", "/signup");
  });
});
