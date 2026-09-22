import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";

const client = vi.hoisted(() => ({
  listAccounts: vi.fn(),
  createAccount: vi.fn(),
  listCategories: vi.fn(),
  createCategory: vi.fn(),
  deleteCategory: vi.fn(),
  recordExpense: vi.fn(),
  recordTransaction: vi.fn(),
  listTransactions: vi.fn(),
  netWorth: vi.fn(),
  cashFlow: vi.fn(),
  importBank: vi.fn(),
  listBills: vi.fn(),
  registerBill: vi.fn(),
  updateBill: vi.fn(),
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

function goToBillsScreen(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

async function billsSection(heading: string): Promise<HTMLElement> {
  return (await screen.findByRole("heading", { name: heading })).closest("section")!;
}

describe("FinancePage", () => {
  beforeEach(() => {
    client.listAccounts.mockResolvedValue([
      { account_id: "a1", name: "Conta Corrente", currency: "BRL", created_at: "x" },
    ]);
    client.createAccount.mockResolvedValue({ account_id: "a2" });
    client.listCategories.mockResolvedValue([
      { category_id: "c1", name: "Moradia", created_at: "x" },
    ]);
    client.createCategory.mockResolvedValue({ category_id: "c2", name: "Mercado", created_at: "x" });
    client.deleteCategory.mockResolvedValue(undefined);
    client.recordExpense.mockResolvedValue({ event_id: "e1" });
    client.recordTransaction.mockResolvedValue({ event_id: "e2" });
    client.listTransactions.mockResolvedValue([
      {
        event_id: "t1",
        kind: "expense",
        account_id: "a1",
        amount_minor: -4599,
        currency: "BRL",
        description: "Almoço",
        category: "Alimentos e bebidas",
        occurred_at: "2026-09-20T12:00:00Z",
      },
      {
        event_id: "t2",
        kind: "import",
        account_id: "a1",
        amount_minor: 100000,
        currency: "BRL",
        description: "Salário",
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
        max_occurrences: 0,
        occurrence_anchor_year: 2026,
        occurrence_anchor_month: 9,
        active: true,
        created_at: "x",
      },
    ]);
    client.registerBill.mockResolvedValue({ bill_id: "b2" });
    client.updateBill.mockResolvedValue({ bill_id: "b1" });
    client.cancelBill.mockResolvedValue(undefined);
    client.payBill.mockResolvedValue({ event_id: "p1" });
    client.billsReport.mockResolvedValue([
      {
        bill_id: "b1",
        account_id: "a1",
        payee: "Aluguel",
        category: "moradia",
        currency: "BRL",
        amount_minor: 250000,
        period: "2026-09-05",
        due_at: "2026-09-05T00:00:00Z",
        paid: false,
        paid_at: null,
        overdue: false,
      },
    ]);
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

  it("mostra a aba Visão geral por padrão, com patrimônio líquido e gastos por categoria", async () => {
    render(<FinancePage />);
    expect(await screen.findByText("BRL -253,89")).toBeInTheDocument();
    expect(await screen.findByText("Alimentos e bebidas")).toBeInTheDocument();
  });

  it("cria uma conta na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Poupança" } });
    fireEvent.click(screen.getByText("Abrir conta"));
    await waitFor(() => expect(client.createAccount).toHaveBeenCalledWith("Poupança", "BRL"));
  });

  it("mostra a dica de consentimento em uma importação bancária com 403 na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    fireEvent.change(await screen.findByLabelText("ID da conta"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("CSV"), { target: { value: "a,b" } });
    fireEvent.click(screen.getByText("Importar"));
    expect(await screen.findByText(/Conceda o consentimento 'bank' primeiro/)).toBeInTheDocument();
  });

  it("mostra a tabela de transações com cards e categorias", async () => {
    render(<FinancePage />);
    goToTab("Transações");

    expect(await screen.findByText("Almoço")).toBeInTheDocument();
    expect(screen.getByText("Salário")).toBeInTheDocument();
    expect(screen.getByText("Alimentos e bebidas")).toBeInTheDocument();
    expect(screen.getByText("Sem categoria")).toBeInTheDocument();
    // Cards: 2 transações, uma despesa (R$45,99) e uma receita (R$1.000,00).
    // Cada valor também aparece na linha da tabela — duas ocorrências.
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("BRL -45,99")).toHaveLength(2);
    expect(screen.getAllByText("BRL 1.000,00")).toHaveLength(2);
  });

  it("filtra transações pela busca", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Almoço");

    fireEvent.change(screen.getByLabelText("Buscar transações"), {
      target: { value: "Salário" },
    });

    expect(screen.queryByText("Almoço")).not.toBeInTheDocument();
    expect(screen.getByText("Salário")).toBeInTheDocument();
  });

  it("registra uma nova transação a partir da aba Transações", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Almoço");

    fireEvent.click(screen.getByText("+ Nova Transação"));
    await waitFor(() => expect(screen.getByLabelText("Conta")).toHaveValue("a1"));
    fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "12.00" } });
    fireEvent.change(screen.getByLabelText("Descrição"), { target: { value: "Café" } });
    fireEvent.click(screen.getByText("Salvar"));

    await waitFor(() =>
      expect(client.recordExpense).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: "a1", amount_minor: 1200, description: "Café" }),
      ),
    );
  });

  it("mostra o detalhamento por categoria na aba Visão geral", async () => {
    render(<FinancePage />);
    const section = await billsSection("Gastos por categoria");
    expect(within(section).getByText("Alimentos e bebidas")).toBeInTheDocument();
    expect(within(section).getByText("Sem categoria")).toBeInTheDocument();
  });

  it("lista, cadastra e exclui uma categoria na aba Categorias", async () => {
    render(<FinancePage />);
    goToTab("Categorias");
    goToBillsScreen("Categorias cadastradas");
    const listSection = await billsSection("Categorias cadastradas");
    expect(within(listSection).getByText("Moradia")).toBeInTheDocument();

    goToBillsScreen("Cadastrar categoria");
    const registerSection = await billsSection("Cadastrar categoria");
    fireEvent.change(within(registerSection).getByLabelText("Nome"), {
      target: { value: "Mercado" },
    });
    fireEvent.click(within(registerSection).getByText("Cadastrar"));
    await waitFor(() => expect(client.createCategory).toHaveBeenCalledWith("Mercado"));

    goToBillsScreen("Categorias cadastradas");
    const listSectionAgain = await billsSection("Categorias cadastradas");
    fireEvent.click(within(listSectionAgain).getByText("Excluir"));
    await waitFor(() => expect(client.deleteCategory).toHaveBeenCalledWith("c1"));
  });

  it("lista as contas cadastradas em tabela e cancela uma", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    goToBillsScreen("Contas cadastradas");
    const section = await billsSection("Contas cadastradas");
    expect(within(section).getByText("Aluguel")).toBeInTheDocument();
    expect(within(section).getByText("Ilimitada")).toBeInTheDocument();
    expect(within(section).getByText("2.500,00 BRL")).toBeInTheDocument();

    fireEvent.click(within(section).getByText("Cancelar"));
    await waitFor(() => expect(client.cancelBill).toHaveBeenCalledWith("b1"));
  });

  it("edita uma conta cadastrada", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    goToBillsScreen("Contas cadastradas");
    const section = await billsSection("Contas cadastradas");
    fireEvent.click(within(section).getByText("Editar"));

    await within(section).findByText("Editar conta a pagar");
    expect(within(section).getByLabelText("Mês/ano base das ocorrências")).toHaveValue("2026-09");
    fireEvent.change(within(section).getByLabelText("Beneficiário"), {
      target: { value: "Aluguel novo" },
    });
    fireEvent.change(within(section).getByLabelText("Ocorrências (0 = infinita)"), {
      target: { value: "12" },
    });
    fireEvent.click(within(section).getByText("Salvar"));

    await waitFor(() =>
      expect(client.updateBill).toHaveBeenCalledWith(
        "b1",
        expect.objectContaining({
          payee: "Aluguel novo",
          max_occurrences: 12,
          occurrence_anchor_year: 2026,
          occurrence_anchor_month: 9,
        }),
      ),
    );
  });

  it("cadastra uma conta mensal", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    const section = await billsSection("Cadastrar conta a pagar");

    fireEvent.change(within(section).getByLabelText("Conta"), { target: { value: "a1" } });
    fireEvent.change(within(section).getByLabelText("Beneficiário"), {
      target: { value: "Netflix" },
    });
    fireEvent.change(within(section).getByLabelText("Valor"), { target: { value: "49.90" } });
    expect(within(section).getByLabelText("Mês/ano base das ocorrências")).toBeInTheDocument();
    fireEvent.change(within(section).getByLabelText("Categoria"), { target: { value: "Moradia" } });
    fireEvent.click(within(section).getByText("Cadastrar"));

    await waitFor(() =>
      expect(client.registerBill).toHaveBeenCalledWith(
        expect.objectContaining({
          account_id: "a1",
          payee: "Netflix",
          amount_minor: 4990,
          category: "Moradia",
          recurrence: "monthly",
          due_day: 5,
          occurrence_anchor_year: expect.any(Number),
          occurrence_anchor_month: expect.any(Number),
        }),
      ),
    );
  });

  it("marca uma fatura como paga direto na lista de vencimentos", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    goToBillsScreen("Faturas e pagamento");
    const section = await billsSection("Faturas e pagamento");

    fireEvent.click(await within(section).findByText("Marcar como paga"));

    await waitFor(() =>
      expect(client.payBill).toHaveBeenCalledWith("b1", "2026-09-05T00:00:00Z"),
    );
  });

  it("salva as preferências de notificação na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Preferências de alerta de vencimento");

    fireEvent.click(within(section).getByLabelText("WhatsApp"));
    fireEvent.change(within(section).getByLabelText("Número do WhatsApp"), {
      target: { value: "+5511999999999" },
    });
    fireEvent.click(within(section).getByText("Salvar"));

    await waitFor(() =>
      expect(client.setNotificationPreferences).toHaveBeenCalledWith({
        email_enabled: true,
        whatsapp_enabled: true,
        whatsapp_phone: "+5511999999999",
      }),
    );
  });
});
