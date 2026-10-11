import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({ myGroup: vi.fn() }));
const me = vi.hoisted(() => ({ value: { user: { user_id: "member" }, status: "ready" } }));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));
vi.mock("../../auth/MeContext", () => ({ useOptionalMe: () => me.value }));

import { SharedFinanceBanner } from "./SharedFinanceBanner";

const GROUP = {
  household_id: "g1",
  name: "Família",
  owner_user_id: "owner",
  created_at: "2026-10-01T00:00:00Z",
  members: [
    { user_id: "member", display_name: "Miro", email: "m@example.com" },
    { user_id: "owner", display_name: "Olga", email: "o@example.com" },
  ],
};

describe("SharedFinanceBanner", () => {
  beforeEach(() => client.myGroup.mockReset());

  it("tells a member whose ledger they see", async () => {
    client.myGroup.mockResolvedValue(GROUP);
    render(<SharedFinanceBanner />);
    expect(await screen.findByRole("status")).toHaveTextContent("dados de Finanças de Olga");
  });

  it("tells the owner who they share with", async () => {
    me.value = { user: { user_id: "owner" }, status: "ready" };
    client.myGroup.mockResolvedValue(GROUP);
    render(<SharedFinanceBanner />);
    expect(await screen.findByRole("status")).toHaveTextContent("compartilhados com Miro");
  });

  it("renders nothing outside a group", async () => {
    client.myGroup.mockResolvedValue(null);
    const { container } = render(<SharedFinanceBanner />);
    await vi.waitFor(() => expect(client.myGroup).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
