import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";

const client = vi.hoisted(() => ({
  listAccounts: vi.fn(),
  createAccount: vi.fn(),
  recordExpense: vi.fn(),
  recordTransaction: vi.fn(),
  listTransactions: vi.fn(),
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

function goToTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

describe("FinancePage", () => {
  beforeEach(() => {
    client.listAccounts.mockResolvedValue([
      { account_id: "a1", name: "Checking", currency: "BRL", created_at: "x" },
    ]);
    client.createAccount.mockResolvedValue({ account_id: "a2" });
    client.recordExpense.mockResolvedValue({ event_id: "e1" });
    client.recordTransaction.mockResolvedValue({ event_id: "e2" });
    client.listTransactions.mockResolvedValue([
      {
        event_id: "t1",
        kind: "expense",
        account_id: "a1",
        amount_minor: -4599,
        currency: "BRL",
        description: "Lunch",
        category: "Alimentos e bebidas",
        occurred_at: "2026-09-20T12:00:00Z",
      },
      {
        event_id: "t2",
        kind: "import",
        account_id: "a1",
        amount_minor: 100000,
        currency: "BRL",
        description: "Salary",
        category: null,
        occurred_at: "2026-09-19T12:00:00Z",
      },
    ]);
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

  it("shows the Visão geral tab by default with accounts and net worth", async () => {
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

  it("surfaces a 403 bank import as a consent hint", async () => {
    render(<FinancePage />);
    fireEvent.change(await screen.findByLabelText("Account id"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("CSV"), { target: { value: "a,b" } });
    fireEvent.click(screen.getByText("Import"));
    expect(await screen.findByText(/Grant the 'bank' consent first/)).toBeInTheDocument();
  });

  it("shows the transactions table with stat cards and category badges", async () => {
    render(<FinancePage />);
    goToTab("Transações");

    expect(await screen.findByText("Lunch")).toBeInTheDocument();
    expect(screen.getByText("Salary")).toBeInTheDocument();
    expect(screen.getByText("Alimentos e bebidas")).toBeInTheDocument();
    expect(screen.getByText("Sem categoria")).toBeInTheDocument();
    // Stat cards: 2 transactions, one expense (R$45.99) and one income (R$1000.00).
    // Each value also appears once in the table row, so expect two matches.
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("BRL -45.99")).toHaveLength(2);
    expect(screen.getAllByText("BRL 1000.00")).toHaveLength(2);
  });

  it("filters transactions by search", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Lunch");

    fireEvent.change(screen.getByLabelText("Buscar transações"), {
      target: { value: "Salary" },
    });

    expect(screen.queryByText("Lunch")).not.toBeInTheDocument();
    expect(screen.getByText("Salary")).toBeInTheDocument();
  });

  it("records a new transaction from the Transações tab", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Lunch");

    fireEvent.click(screen.getByText("+ Nova Transação"));
    await waitFor(() => expect(screen.getByLabelText("Account")).toHaveValue("a1"));
    fireEvent.change(screen.getByLabelText("Amount (minor units)"), {
      target: { value: "1200" },
    });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Coffee" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(client.recordExpense).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: "a1", amount_minor: 1200, description: "Coffee" }),
      ),
    );
  });

  it("shows a category breakdown on the Categorias tab", async () => {
    render(<FinancePage />);
    goToTab("Categorias");
    expect(await screen.findByText("Alimentos e bebidas")).toBeInTheDocument();
    expect(screen.getByText("Sem categoria")).toBeInTheDocument();
  });

  it("lists bills and cancels one", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    expect(await screen.findByText("Aluguel")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => expect(client.cancelBill).toHaveBeenCalledWith("b1"));
  });

  it("registers a monthly bill", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    await screen.findByText("Aluguel");

    const billsSection = screen.getByText("Bills (contas a pagar)").closest("section")!;
    fireEvent.change(
      within(billsSection).getByLabelText("Account id"),
      { target: { value: "a1" } },
    );
    fireEvent.change(within(billsSection).getByLabelText("Payee"), {
      target: { value: "Netflix" },
    });
    fireEvent.change(within(billsSection).getByLabelText("Amount (minor units)"), {
      target: { value: "4990" },
    });
    fireEvent.click(within(billsSection).getByText("Register bill"));

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
    goToTab("Contas a pagar");
    await screen.findByText("Aluguel");

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
    goToTab("Contas a pagar");
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
