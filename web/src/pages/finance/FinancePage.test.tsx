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
  listBills: vi.fn(),
  registerBill: vi.fn(),
  cancelBill: vi.fn(),
  payBill: vi.fn(),
  billsReport: vi.fn(),
  runBillAlerts: vi.fn(),
  getNotificationPreferences: vi.fn(),
  setNotificationPreferences: vi.fn(),
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
    client.listBills.mockResolvedValue([
      {
        bill_id: "b1",
        account_id: "a1",
        payee: "Aluguel",
        amount_minor: 250000,
        currency: "BRL",
        category: "moradia",
        recurrence: "monthly",
        due_day: 5,
        due_at: null,
        active: true,
        created_at: "x",
      },
    ]);
    client.registerBill.mockResolvedValue({ bill_id: "b2" });
    client.cancelBill.mockResolvedValue(undefined);
    client.payBill.mockResolvedValue({ event_id: "p1" });
    client.billsReport.mockResolvedValue([]);
    client.runBillAlerts.mockResolvedValue([]);
    client.getNotificationPreferences.mockResolvedValue({
      email_enabled: true,
      whatsapp_enabled: false,
      whatsapp_phone: null,
      updated_at: "x",
    });
    client.setNotificationPreferences.mockResolvedValue({
      email_enabled: true,
      whatsapp_enabled: false,
      whatsapp_phone: null,
      updated_at: "x",
    });
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
    fireEvent.change(screen.getAllByLabelText("Amount (minor units)")[0], {
      target: { value: "4599" },
    });
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
    // Field order: Record expense, Bank CSV import, Bills — Bank CSV import is index 1.
    const accountFields = screen.getAllByLabelText("Account id");
    fireEvent.change(accountFields[1], { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("CSV"), { target: { value: "a,b" } });
    fireEvent.click(screen.getByText("Import"));
    expect(await screen.findByText(/Grant the 'bank' consent first/)).toBeInTheDocument();
  });

  it("lists bills and cancels one", async () => {
    render(<FinancePage />);
    expect(await screen.findByText("Aluguel")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => expect(client.cancelBill).toHaveBeenCalledWith("b1"));
  });

  it("registers a monthly bill", async () => {
    render(<FinancePage />);
    // Field order: Record expense, Bank CSV import, Bills — Bills is index 2.
    fireEvent.change(screen.getAllByLabelText("Account id")[2], { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Payee"), { target: { value: "Netflix" } });
    // "Amount (minor units)" also appears in Record expense — Bills is index 1.
    fireEvent.change(screen.getAllByLabelText("Amount (minor units)")[1], {
      target: { value: "4990" },
    });
    fireEvent.click(screen.getByText("Register bill"));
    await waitFor(() =>
      expect(client.registerBill).toHaveBeenCalledWith(
        expect.objectContaining({
          account_id: "a1",
          payee: "Netflix",
          amount_minor: 4990,
          recurrence: "monthly",
          due_day: 5,
        }),
      ),
    );
  });

  it("marks a bill as paid", async () => {
    render(<FinancePage />);
    fireEvent.change(screen.getByLabelText("Bill id"), { target: { value: "b1" } });
    fireEvent.change(screen.getByLabelText("Due date (occurrence)"), {
      target: { value: "2026-09-05T00:00" },
    });
    fireEvent.click(screen.getByText("Mark as paid"));
    await waitFor(() =>
      expect(client.payBill).toHaveBeenCalledWith(
        "b1",
        new Date("2026-09-05T00:00").toISOString(),
        undefined,
      ),
    );
  });

  it("saves notification preferences", async () => {
    render(<FinancePage />);
    await screen.findByText("Reminder preferences");
    fireEvent.click(screen.getByLabelText("WhatsApp"));
    fireEvent.change(screen.getByLabelText("WhatsApp number"), {
      target: { value: "+5511999999999" },
    });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(client.setNotificationPreferences).toHaveBeenCalledWith({
        email_enabled: true,
        whatsapp_enabled: true,
        whatsapp_phone: "+5511999999999",
      }),
    );
  });
});
