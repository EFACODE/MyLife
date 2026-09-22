import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../../auth/AuthContext";

const client = vi.hoisted(() => ({ exportMe: vi.fn(), deleteMe: vi.fn() }));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { PrivacyPage } from "./PrivacyPage";

function renderPage() {
  return render(
    <AuthProvider>
      <PrivacyPage />
    </AuthProvider>,
  );
}

describe("PrivacyPage", () => {
  beforeEach(() => {
    localStorage.clear();
    client.exportMe.mockResolvedValue({
      user: {},
      consents: [{ scope: "bank" }],
      audit: [],
      events: [1, 2],
      raw_records: [],
      entities: [],
      relationships: [],
      accounts: [],
      goals: [],
      documents: [],
    });
    client.deleteMe.mockResolvedValue({ deleted: { events: 2 } });
  });

  it("exports data and shows counts", async () => {
    renderPage();
    fireEvent.click(screen.getByText("Exportar"));
    const row = await screen.findByText(
      (_, el) => el?.tagName === "LI" && el.textContent === "events: 2",
    );
    expect(row).toBeInTheDocument();
  });

  it("erases the account after confirmation", async () => {
    localStorage.setItem("mylife.token", "t");
    renderPage();
    fireEvent.click(screen.getByText("Apagar conta"));
    fireEvent.click(screen.getByText("Confirmar exclusão"));
    await waitFor(() => expect(client.deleteMe).toHaveBeenCalled());
    expect(localStorage.getItem("mylife.token")).toBeNull();
  });
});
