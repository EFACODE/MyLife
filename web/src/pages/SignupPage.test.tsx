import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { SignupPage } from "./SignupPage";

function renderPage() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/signup"]}>
        <Routes>
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/" element={<div>home page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

function fillForm() {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Ada Lovelace" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ada@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "supersecret1" } });
}

describe("SignupPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("registers, logs in and lands on the home page", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ user_id: "u1", email: "ada@example.com" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: "tok123", token_type: "bearer" }),
      } as Response);

    renderPage();
    fillForm();
    fireEvent.click(screen.getByText("Sign up"));

    await waitFor(() => expect(screen.getByText("home page")).toBeInTheDocument());
    expect(localStorage.getItem("mylife.token")).toBe("tok123");

    const [registerCall] = fetchMock.mock.calls;
    expect(registerCall[0]).toBe("/users");
    expect((registerCall[1] as RequestInit).body).toBe(
      JSON.stringify({
        email: "ada@example.com",
        display_name: "Ada Lovelace",
        password: "supersecret1",
      }),
    );
  });

  it("shows a message when the email is already registered", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({}) } as Response);

    renderPage();
    fillForm();
    fireEvent.click(screen.getByText("Sign up"));

    await waitFor(() =>
      expect(screen.getByText("An account with this email already exists.")).toBeInTheDocument(),
    );
  });

  it("links back to the login page", () => {
    renderPage();
    expect(screen.getByText("Sign in").closest("a")).toHaveAttribute("href", "/login");
  });
});
