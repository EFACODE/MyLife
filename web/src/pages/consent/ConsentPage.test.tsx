import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  listConsents: vi.fn(),
  grantConsent: vi.fn(),
  revokeConsent: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { ConsentPage } from "./ConsentPage";

describe("ConsentPage", () => {
  beforeEach(() => {
    client.listConsents.mockResolvedValue([{ scope: "bank", granted: true, updated_at: "x" }]);
    client.grantConsent.mockResolvedValue({ scope: "health", granted: true, updated_at: "x" });
    client.revokeConsent.mockResolvedValue(undefined);
  });

  it("lists the user's consents", async () => {
    render(<ConsentPage />);
    expect(await screen.findByText("bank")).toBeInTheDocument();
  });

  it("grants a consent for the entered scope", async () => {
    render(<ConsentPage />);
    await screen.findByText("bank");
    fireEvent.change(screen.getByLabelText(/Escopo/), { target: { value: "health" } });
    fireEvent.click(screen.getByText("Conceder"));
    await waitFor(() => expect(client.grantConsent).toHaveBeenCalledWith("health"));
  });

  it("revokes a granted consent", async () => {
    render(<ConsentPage />);
    fireEvent.click(await screen.findByText("Revogar"));
    await waitFor(() => expect(client.revokeConsent).toHaveBeenCalledWith("bank"));
  });
});
