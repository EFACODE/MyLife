import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";

const client = vi.hoisted(() => ({
  listAccounts: vi.fn(),
  createAccount: vi.fn(),
  recordExpense: vi.fn(),
  netWorth: vi.fn(),
  cashFlow: vi.fn(),
  importBank: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { FinancePage } from "./FinancePage";

describe("FinancePage", () => {
  beforeEach(() => {
    client.listAccounts.mockResolvedValue([
      { account_id: "a1", name: "Checking", currency: "BRL", created_at: "x" },
    ]);
    client.createAccount.mockResolvedValue({ account_id: "a2" });
    client.recordExpense.mockResolvedValue({ event_id: "e1" });
    client.netWorth.mockResolvedValue({
      currencies: [{ currency: "BRL", total_minor: -25389 }],
      accounts: [],
    });
    client.cashFlow.mockResolvedValue({ occurred_from: "x", occurred_to: "y", flows: [] });
    client.importBank.mockRejectedValue(new ApiError(403, "forbidden"));
  });

  it("lists accounts and net worth", async () => {
    render(<FinancePage />);
    expect(await screen.findByText("Checking")).toBeInTheDocument();
    expect(await screen.findByText("BRL -253.89")).toBeInTheDocument();
  });

  it("creates an account", async () => {
    render(<FinancePage />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Savings" } });
    fireEvent.click(screen.getByText("Open account"));
    await waitFor(() => expect(client.createAccount).toHaveBeenCalledWith("Savings", "BRL"));
  });

  it("records an expense in minor units", async () => {
    render(<FinancePage />);
    fireEvent.change(screen.getAllByLabelText("Account id")[0], { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Amount (minor units)"), { target: { value: "4599" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Lunch" } });
    fireEvent.click(screen.getByText("Record"));
    await waitFor(() =>
      expect(client.recordExpense).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: "a1", amount_minor: 4599, description: "Lunch" }),
      ),
    );
  });

  it("surfaces a 403 bank import as a consent hint", async () => {
    render(<FinancePage />);
    const accountFields = screen.getAllByLabelText("Account id");
    fireEvent.change(accountFields[accountFields.length - 1], { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("CSV"), { target: { value: "a,b" } });
    fireEvent.click(screen.getByText("Import"));
    expect(await screen.findByText(/Grant the 'bank' consent first/)).toBeInTheDocument();
  });
});
