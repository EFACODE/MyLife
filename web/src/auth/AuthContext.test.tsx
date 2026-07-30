import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";

function Probe() {
  const { isAuthenticated, login, logout } = useAuth();
  return (
    <div>
      <span>{isAuthenticated ? "in" : "out"}</span>
      <button type="button" onClick={() => login("t")}>
        login
      </button>
      <button type="button" onClick={logout}>
        logout
      </button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => localStorage.clear());

  it("logs in and out, persisting the token", () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByText("out")).toBeInTheDocument();

    act(() => screen.getByText("login").click());
    expect(screen.getByText("in")).toBeInTheDocument();
    expect(localStorage.getItem("mylife.token")).toBe("t");

    act(() => screen.getByText("logout").click());
    expect(screen.getByText("out")).toBeInTheDocument();
    expect(localStorage.getItem("mylife.token")).toBeNull();
  });
});
