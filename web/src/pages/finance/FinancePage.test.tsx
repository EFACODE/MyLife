import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";

const client = vi.hoisted(() => ({
  listAccounts: vi.fn(),
  createAccount: vi.fn(),
  renameAccount: vi.fn(),
  deleteAccount: vi.fn(),
  listCategories: vi.fn(),
  createCategory: vi.fn(),
  deleteCategory: vi.fn(),
  recordExpense: vi.fn(),
  recordTransaction: vi.fn(),
  listTransactions: vi.fn(),
  updateTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  netWorth: vi.fn(),
  openFinanceStatus: vi.fn(),
  connectOpenFinance: vi.fn(),
  disconnectOpenFinance: vi.fn(),
  syncOpenFinance: vi.fn(),
  grantConsent: vi.fn(),
  listBills: vi.fn(),
  registerBill: vi.fn(),
  updateBill: vi.fn(),
  cancelBill: vi.fn(),
  payBill: vi.fn(),
  billsReport: vi.fn(),
  runBillAlerts: vi.fn(),
  getNotificationPreferences: vi.fn(),
  setNotificationPreferences: vi.fn(),
  listAlertEmails: vi.fn(),
  addAlertEmail: vi.fn(),
  deleteAlertEmail: vi.fn(),
  listAlertPhones: vi.fn(),
  addAlertPhone: vi.fn(),
  deleteAlertPhone: vi.fn(),
  me: vi.fn(),
  updateCurrentUser: vi.fn(),
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
    // Fixa o "hoje" no mesmo mês das transações mockadas (setembro/2026), já
    // que a aba Visão geral filtra o gráfico de gastos pelo mês atual por padrão.
    vi.setSystemTime(new Date("2026-09-20T12:00:00Z"));
    client.listAccounts.mockResolvedValue([
      { account_id: "a1", name: "Conta Corrente", currency: "BRL", created_at: "x" },
    ]);
    client.createAccount.mockResolvedValue({ account_id: "a2" });
    client.renameAccount.mockResolvedValue({
      account_id: "a1",
      name: "Conta Renomeada",
      currency: "BRL",
      created_at: "x",
    });
    client.deleteAccount.mockResolvedValue(undefined);
    client.listCategories.mockResolvedValue([
      { category_id: "c1", name: "Moradia", created_at: "x" },
    ]);
    client.createCategory.mockResolvedValue({ category_id: "c2", name: "Mercado", created_at: "x" });
    client.deleteCategory.mockResolvedValue(undefined);
    client.recordExpense.mockResolvedValue({ event_id: "e1" });
    client.recordTransaction.mockResolvedValue({ event_id: "e2" });
    client.updateTransaction.mockResolvedValue({ event_id: "t1" });
    client.deleteTransaction.mockResolvedValue(undefined);
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
      accounts: [{ account_id: "a1", currency: "BRL", balance_minor: -25389, as_of: "x" }],
    });
    client.openFinanceStatus.mockResolvedValue({ connected: false, updated_at: null });
    client.connectOpenFinance.mockResolvedValue(undefined);
    client.disconnectOpenFinance.mockResolvedValue(undefined);
    client.syncOpenFinance.mockResolvedValue({
      source: "openfinance",
      raw_ingested: 3,
      events_created: 3,
      skipped_duplicates: 0,
    });
    client.grantConsent.mockResolvedValue({ scope: "openfinance", granted: true });
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
      updated_at: "x",
    });
    client.setNotificationPreferences.mockResolvedValue({
      email_enabled: true,
      whatsapp_enabled: false,
      updated_at: "x",
    });
    client.listAlertEmails.mockResolvedValue([]);
    client.addAlertEmail.mockResolvedValue({
      alert_email_id: "ae1",
      email: "spouse@example.com",
      created_at: "x",
    });
    client.deleteAlertEmail.mockResolvedValue(undefined);
    client.listAlertPhones.mockResolvedValue([]);
    client.addAlertPhone.mockResolvedValue({
      alert_phone_id: "ap1",
      phone: "+5511999999999",
      created_at: "x",
    });
    client.deleteAlertPhone.mockResolvedValue(undefined);
    client.me.mockResolvedValue({
      user_id: "u1",
      email: "ada@example.com",
      display_name: "Ada",
      status: "active",
      household_id: null,
      created_at: "x",
    });
    client.updateCurrentUser.mockResolvedValue({
      user_id: "u1",
      email: "ada@example.com",
      display_name: "Ada Lovelace",
      status: "active",
      household_id: null,
      created_at: "x",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("mostra a aba Visão geral por padrão, com os gastos por categoria", async () => {
    render(<FinancePage />);
    expect(await screen.findByText("Alimentos e bebidas")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Gastos por categoria" })).toBeInTheDocument();
  });

  it("filtra o gráfico de gastos por categoria pelo período selecionado", async () => {
    render(<FinancePage />);
    expect(await screen.findByText("Alimentos e bebidas")).toBeInTheDocument();

    const section = await billsSection("Gastos por categoria");
    expect(within(section).getByText("Setembro de 2026")).toBeInTheDocument();

    fireEvent.click(within(section).getByRole("button", { name: "Mês anterior" }));
    expect(within(section).getByText("Agosto de 2026")).toBeInTheDocument();
    expect(within(section).queryByText("Alimentos e bebidas")).not.toBeInTheDocument();
    expect(
      within(section).getByText(
        "Nenhuma transação ainda — as categorias aparecerão aqui assim que você registrar alguma.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(within(section).getByRole("button", { name: "Próximo mês" }));
    expect(within(section).getByText("Setembro de 2026")).toBeInTheDocument();
    expect(within(section).getByText("Alimentos e bebidas")).toBeInTheDocument();
  });

  it("mostra o saldo das contas na aba Configurações, ocultando contas zeradas", async () => {
    client.listAccounts.mockResolvedValue([
      { account_id: "a1", name: "Conta Corrente", currency: "BRL", created_at: "x" },
      { account_id: "a2", name: "Conta Zerada", currency: "BRL", created_at: "x" },
    ]);
    client.netWorth.mockResolvedValue({
      currencies: [{ currency: "BRL", total_minor: -25389 }],
      accounts: [
        { account_id: "a1", currency: "BRL", balance_minor: -25389, as_of: "x" },
        { account_id: "a2", currency: "BRL", balance_minor: 0, as_of: "x" },
      ],
    });

    render(<FinancePage />);
    expect(screen.queryByRole("heading", { name: "Saldo das contas" })).not.toBeInTheDocument();
    goToTab("Configurações");
    const section = await billsSection("Saldo das contas");
    expect(await within(section).findByText("Conta Corrente")).toBeInTheDocument();
    expect(within(section).getByText("-253,89 BRL")).toBeInTheDocument();
    expect(within(section).queryByText("Conta Zerada")).not.toBeInTheDocument();
  });

  it("recarrega o saldo das contas depois de abrir uma conta", async () => {
    const accounts = [{ account_id: "a1", name: "Conta Corrente", currency: "BRL", created_at: "x" }];
    client.listAccounts.mockImplementation(async () => [...accounts]);
    client.netWorth.mockClear();
    render(<FinancePage />);
    goToTab("Configurações");
    await billsSection("Saldo das contas");
    await waitFor(() => expect(client.listAccounts).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    const callsBefore = client.netWorth.mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);

    const section = await billsSection("Contas");
    fireEvent.change(within(section).getByLabelText("Nome"), { target: { value: "Poupança" } });
    fireEvent.click(within(section).getByText("Abrir conta"));
    await waitFor(() => expect(client.createAccount).toHaveBeenCalled());
    await waitFor(() => expect(client.netWorth.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it("cria uma conta na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Contas");
    fireEvent.change(within(section).getByLabelText("Nome"), { target: { value: "Poupança" } });
    fireEvent.click(within(section).getByText("Abrir conta"));
    await waitFor(() => expect(client.createAccount).toHaveBeenCalledWith("Poupança", "BRL"));
  });

  it("renomeia uma conta na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Contas");
    fireEvent.click(within(section).getByText("Editar"));
    const editForm = within(section).getByText("Salvar").closest("form")!;
    fireEvent.change(within(editForm).getByLabelText("Nome"), {
      target: { value: "Conta Renomeada" },
    });
    fireEvent.click(within(editForm).getByText("Salvar"));
    await waitFor(() =>
      expect(client.renameAccount).toHaveBeenCalledWith("a1", "Conta Renomeada"),
    );
  });

  it("exclui uma conta sem transações na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Contas");
    fireEvent.click(within(section).getByText("Excluir"));
    await waitFor(() => expect(client.deleteAccount).toHaveBeenCalledWith("a1"));
  });

  it("avisa para renomear em vez de excluir uma conta com transações", async () => {
    client.deleteAccount.mockRejectedValue(new ApiError(409, "has activity"));
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Contas");
    fireEvent.click(within(section).getByText("Excluir"));
    expect(
      await within(section).findByText(/Renomeie a conta em vez de excluí-la/),
    ).toBeInTheDocument();
  });

  it("conecta a Pierre Finance informando a chave de API na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    fireEvent.change(await screen.findByLabelText("Chave de API (sk-...)"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByText("Conectar"));
    await waitFor(() => expect(client.connectOpenFinance).toHaveBeenCalledWith("sk-test"));
  });

  it("avisa quando a chave é aceita mas o status continua desconectado", async () => {
    // connectOpenFinance resolves (the key was accepted), but the status
    // check right after still reports not connected — most likely a
    // MYLIFE_CREDENTIAL_ENCRYPTION_KEY that isn't pinned across processes.
    client.openFinanceStatus.mockResolvedValue({ connected: false, updated_at: null });
    render(<FinancePage />);
    goToTab("Configurações");
    fireEvent.change(await screen.findByLabelText("Chave de API (sk-...)"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByText("Conectar"));

    expect(
      await screen.findByText(/A chave foi enviada, mas o status ainda mostra desconectado/),
    ).toBeInTheDocument();
  });

  it("mostra sincronizar/desconectar quando a Pierre Finance já está conectada", async () => {
    client.openFinanceStatus.mockResolvedValue({
      connected: true,
      updated_at: "2026-09-24T00:00:00Z",
    });
    render(<FinancePage />);
    goToTab("Configurações");

    expect(await screen.findByText(/Conectado desde/)).toBeInTheDocument();
    client.listAccounts.mockClear();
    client.listTransactions.mockClear();
    fireEvent.click(screen.getByText("Sincronizar agora"));
    expect(
      await screen.findByText("3 evento(s) importado(s) (0 duplicado(s) ignorado(s))."),
    ).toBeInTheDocument();
    await waitFor(() => expect(client.listAccounts).toHaveBeenCalled());
    await waitFor(() => expect(client.listTransactions).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Desconectar"));
    await waitFor(() => expect(client.disconnectOpenFinance).toHaveBeenCalled());
  });

  it("faz backfill a partir de uma data escolhida na aba Configurações", async () => {
    client.openFinanceStatus.mockResolvedValue({
      connected: true,
      updated_at: "2026-09-24T00:00:00Z",
    });
    render(<FinancePage />);
    goToTab("Configurações");

    await screen.findByText(/Conectado desde/);
    fireEvent.change(screen.getByLabelText("Buscar desde (backfill)"), {
      target: { value: "2026-09-01" },
    });
    fireEvent.click(screen.getByText("Sincronizar a partir dessa data"));

    await waitFor(() => expect(client.syncOpenFinance).toHaveBeenCalledWith("2026-09-01"));
  });

  it("mascara a chave de API da Pierre Finance por padrão e permite revelar", async () => {
    render(<FinancePage />);
    goToTab("Configurações");

    const input = await screen.findByLabelText("Chave de API (sk-...)");
    expect(input).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByText("Mostrar"));
    expect(input).toHaveAttribute("type", "text");

    fireEvent.click(screen.getByText("Ocultar"));
    expect(input).toHaveAttribute("type", "password");
  });

  it("não deixa a chave revelada depois de conectar e desconectar de novo", async () => {
    client.openFinanceStatus
      .mockResolvedValueOnce({ connected: false, updated_at: null })
      .mockResolvedValueOnce({ connected: true, updated_at: "2026-09-24T00:00:00Z" })
      .mockResolvedValueOnce({ connected: false, updated_at: null });
    render(<FinancePage />);
    goToTab("Configurações");

    fireEvent.click(await screen.findByText("Mostrar"));
    expect(screen.getByLabelText("Chave de API (sk-...)")).toHaveAttribute("type", "text");

    fireEvent.change(screen.getByLabelText("Chave de API (sk-...)"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByText("Conectar"));
    await screen.findByText(/Conectado desde/);

    fireEvent.click(screen.getByText("Desconectar"));
    const revealedInput = await screen.findByLabelText("Chave de API (sk-...)");
    expect(revealedInput).toHaveAttribute("type", "password");
  });

  it("mostra a dica de consentimento ao sincronizar a Pierre Finance sem consentimento (403)", async () => {
    client.openFinanceStatus.mockResolvedValue({
      connected: true,
      updated_at: "2026-09-24T00:00:00Z",
    });
    client.syncOpenFinance.mockRejectedValue(new ApiError(403, "forbidden"));
    render(<FinancePage />);
    goToTab("Configurações");

    fireEvent.click(await screen.findByText("Sincronizar agora"));
    expect(
      await screen.findByText(/Conceda o consentimento 'openfinance' primeiro/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Conceder consentimento e sincronizar"),
    ).toBeInTheDocument();
  });

  it("concede o consentimento 'openfinance' e sincroniza direto da tela de Finanças", async () => {
    client.openFinanceStatus.mockResolvedValue({
      connected: true,
      updated_at: "2026-09-24T00:00:00Z",
    });
    client.syncOpenFinance
      .mockRejectedValueOnce(new ApiError(403, "forbidden"))
      .mockResolvedValueOnce({
        source: "openfinance",
        raw_ingested: 2,
        events_created: 2,
        skipped_duplicates: 0,
      });
    client.syncOpenFinance.mockClear();
    client.grantConsent.mockClear();
    render(<FinancePage />);
    goToTab("Configurações");

    fireEvent.click(await screen.findByText("Sincronizar agora"));
    fireEvent.click(await screen.findByText("Conceder consentimento e sincronizar"));

    await waitFor(() => expect(client.grantConsent).toHaveBeenCalledWith("openfinance"));
    await waitFor(() => expect(client.syncOpenFinance).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText("2 evento(s) importado(s) (0 duplicado(s) ignorado(s))."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Conceder consentimento e sincronizar")).not.toBeInTheDocument();
  });

  it("avisa para conectar a chave quando a sincronização retorna 409", async () => {
    client.openFinanceStatus.mockResolvedValue({
      connected: true,
      updated_at: "2026-09-24T00:00:00Z",
    });
    client.syncOpenFinance.mockRejectedValue(new ApiError(409, "missing credential"));
    render(<FinancePage />);
    goToTab("Configurações");

    fireEvent.click(await screen.findByText("Sincronizar agora"));
    expect(
      await screen.findByText(/Conecte sua chave de API da Pierre Finance primeiro/),
    ).toBeInTheDocument();
  });

  it("mostra o motivo real da Pierre Finance quando a sincronização falha com outro erro (502)", async () => {
    client.openFinanceStatus.mockResolvedValue({
      connected: true,
      updated_at: "2026-09-24T00:00:00Z",
    });
    client.syncOpenFinance.mockRejectedValue(
      new ApiError(502, "Pierre API error (502): rate limited"),
    );
    render(<FinancePage />);
    goToTab("Configurações");

    fireEvent.click(await screen.findByText("Sincronizar agora"));
    expect(
      await screen.findByText(/Pierre API error \(502\): rate limited/),
    ).toBeInTheDocument();
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

  it("edita uma transação", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Almoço");

    fireEvent.click(screen.getAllByText("Editar")[0]);
    await screen.findByText("Editar transação");

    fireEvent.change(screen.getByLabelText("Descrição"), {
      target: { value: "Almoço corrigido" },
    });
    fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "-50.00" } });
    fireEvent.click(screen.getByText("Salvar"));

    await waitFor(() =>
      expect(client.updateTransaction).toHaveBeenCalledWith(
        "t1",
        expect.objectContaining({ amount_minor: -5000, description: "Almoço corrigido" }),
      ),
    );
  });

  it("exclui uma transação", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Almoço");

    fireEvent.click(screen.getAllByText("Excluir")[0]);

    await waitFor(() => expect(client.deleteTransaction).toHaveBeenCalledWith("t1"));
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

  it("registra uma despesa (valor negativo) com categoria e classificação", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Almoço");

    fireEvent.click(screen.getByText("+ Nova Transação"));
    await waitFor(() => expect(screen.getByLabelText("Conta")).toHaveValue("a1"));
    fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "-12.00" } });
    fireEvent.change(screen.getByLabelText("Descrição"), { target: { value: "Café" } });
    fireEvent.change(screen.getByLabelText("Categoria"), { target: { value: "Moradia" } });
    fireEvent.change(screen.getByLabelText("Classificação"), { target: { value: "fixed" } });
    fireEvent.click(screen.getByText("Salvar"));

    await waitFor(() =>
      expect(client.recordExpense).toHaveBeenCalledWith(
        expect.objectContaining({
          account_id: "a1",
          amount_minor: 1200,
          description: "Café",
          category: "Moradia",
          expense_type: "fixed",
        }),
      ),
    );
  });

  it("registra uma receita (valor positivo) sem enviar classificação", async () => {
    render(<FinancePage />);
    goToTab("Transações");
    await screen.findByText("Almoço");

    fireEvent.click(screen.getByText("+ Nova Transação"));
    await waitFor(() => expect(screen.getByLabelText("Conta")).toHaveValue("a1"));
    fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "500.00" } });
    fireEvent.change(screen.getByLabelText("Descrição"), { target: { value: "Bônus" } });
    expect(screen.getByLabelText("Classificação")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Salvar"));

    await waitFor(() =>
      expect(client.recordTransaction).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: "a1", amount_minor: 50000, description: "Bônus" }),
      ),
    );
  });

  it("mostra o detalhamento por categoria na aba Visão geral", async () => {
    render(<FinancePage />);
    const section = await billsSection("Gastos por categoria");
    expect(within(section).getByText("Alimentos e bebidas")).toBeInTheDocument();
    expect(within(section).getByText("Sem categoria")).toBeInTheDocument();
  });

  it("lista, cadastra e exclui uma categoria na aba Configurações", async () => {
    render(<FinancePage />);
    expect(screen.queryByRole("tab", { name: "Categorias" })).not.toBeInTheDocument();
    goToTab("Configurações");
    const listSection = await billsSection("Categorias cadastradas");
    expect(await within(listSection).findByText("Moradia")).toBeInTheDocument();

    const registerSection = await billsSection("Cadastrar categoria");
    fireEvent.change(within(registerSection).getByLabelText("Nome"), {
      target: { value: "Mercado" },
    });
    fireEvent.click(within(registerSection).getByText("Cadastrar"));
    await waitFor(() => expect(client.createCategory).toHaveBeenCalledWith("Mercado"));

    fireEvent.click(within(listSection).getByText("Excluir"));
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

  it("abre Contas a pagar em Faturas e pagamento, com Cadastrar por último", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    expect(await screen.findByRole("heading", { name: "Faturas e pagamento" })).toBeInTheDocument();
    const subTabs = screen.getAllByRole("tablist")[1];
    expect(within(subTabs).getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Faturas e pagamento",
      "Contas cadastradas",
      "Cadastrar",
    ]);
  });

  it("cadastra uma conta mensal", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    goToBillsScreen("Cadastrar");
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

  it("filtra as faturas ao clicar nos cartões de resumo", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    const card = await screen.findByRole("button", { name: /Vencidas/ });
    expect(card).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
    await waitFor(() =>
      expect(client.billsReport).toHaveBeenLastCalledWith(expect.any(String), expect.any(String), {
        paid: false,
        overdue: true,
      }),
    );
    const section = await billsSection("Faturas e pagamento");
    expect(within(section).getByLabelText("Status")).toHaveValue("false");
    expect(within(section).getByLabelText("Vencimento")).toHaveValue("true");

    fireEvent.click(screen.getByRole("button", { name: /Pagas neste período/ }));
    await waitFor(() =>
      expect(client.billsReport).toHaveBeenLastCalledWith(expect.any(String), expect.any(String), {
        paid: true,
        overdue: undefined,
      }),
    );
    expect(card).toHaveAttribute("aria-pressed", "false");

    // Clicking the active card again clears the filter.
    fireEvent.click(screen.getByRole("button", { name: /Pagas neste período/ }));
    await waitFor(() =>
      expect(client.billsReport).toHaveBeenLastCalledWith(expect.any(String), expect.any(String), {
        paid: undefined,
        overdue: undefined,
      }),
    );
  });

  it("edita valor, data e descrição antes de marcar a fatura como paga", async () => {
    render(<FinancePage />);
    goToTab("Contas a pagar");
    const section = await billsSection("Faturas e pagamento");

    fireEvent.click(await within(section).findByText("Editar e pagar"));
    const form = within(section).getByRole("form", { name: "Editar e pagar Aluguel" });
    expect(within(form).getByLabelText("Valor (BRL)")).toHaveValue(2500);
    expect(within(form).getByLabelText("Descrição")).toHaveValue("Aluguel");

    fireEvent.change(within(form).getByLabelText("Valor (BRL)"), { target: { value: "2612.50" } });
    fireEvent.change(within(form).getByLabelText("Data do pagamento"), {
      target: { value: "2026-09-04" },
    });
    fireEvent.change(within(form).getByLabelText("Descrição"), {
      target: { value: "Aluguel + condomínio" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Confirmar pagamento" }));

    await waitFor(() =>
      expect(client.payBill).toHaveBeenCalledWith("b1", "2026-09-05T00:00:00Z", {
        amountMinor: 261250,
        paidAt: new Date("2026-09-04T12:00").toISOString(),
        description: "Aluguel + condomínio",
      }),
    );
    await waitFor(() =>
      expect(within(section).queryByRole("form", { name: "Editar e pagar Aluguel" })).toBeNull(),
    );
  });

  it("não envia o pagamento com valor zerado", async () => {
    client.payBill.mockClear();
    render(<FinancePage />);
    goToTab("Contas a pagar");
    const section = await billsSection("Faturas e pagamento");

    fireEvent.click(await within(section).findByText("Editar e pagar"));
    const form = within(section).getByRole("form", { name: "Editar e pagar Aluguel" });
    fireEvent.change(within(form).getByLabelText("Valor (BRL)"), { target: { value: "0" } });
    fireEvent.submit(form);

    expect(await within(form).findByText("Informe um valor maior que zero.")).toBeInTheDocument();
    expect(client.payBill).not.toHaveBeenCalled();
  });

  it("mostra o valor pago, a data e a descrição de uma fatura paga", async () => {
    client.billsReport.mockResolvedValue([
      {
        bill_id: "b1",
        account_id: "a1",
        payee: "COPEL",
        category: null,
        currency: "BRL",
        amount_minor: 30000,
        period: "2026-09-09",
        due_at: "2026-09-09T00:00:00Z",
        paid: true,
        paid_at: "2026-09-08T15:00:00Z",
        overdue: false,
        paid_amount_minor: 31250,
        payment_description: "Luz — agosto",
      },
    ]);
    render(<FinancePage />);
    goToTab("Contas a pagar");
    const section = await billsSection("Faturas e pagamento");

    expect(await within(section).findByText("Luz — agosto")).toBeInTheDocument();
    expect(within(section).getByText(/BRL 312,50/)).toBeInTheDocument();
    expect(within(section).getByText(/paga em/)).toBeInTheDocument();
    expect(within(section).queryByText("Editar e pagar")).not.toBeInTheDocument();
  });

  it("salva as preferências de notificação na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Preferências de alerta de vencimento");

    fireEvent.click(within(section).getByLabelText("WhatsApp"));
    fireEvent.click(within(section).getByText("Salvar"));

    await waitFor(() =>
      expect(client.setNotificationPreferences).toHaveBeenCalledWith({
        email_enabled: true,
        whatsapp_enabled: true,
      }),
    );
  });

  it("cadastra um e-mail e um telefone de alerta na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Preferências de alerta de vencimento");

    fireEvent.change(within(section).getByLabelText("E-mail de alerta"), {
      target: { value: "spouse@example.com" },
    });
    fireEvent.click(within(section).getAllByRole("button", { name: "Adicionar" })[0]);
    await waitFor(() => expect(client.addAlertEmail).toHaveBeenCalledWith("spouse@example.com"));

    fireEvent.change(within(section).getByLabelText("Número do WhatsApp"), {
      target: { value: "+5511999999999" },
    });
    fireEvent.click(within(section).getAllByRole("button", { name: "Adicionar" })[1]);
    await waitFor(() =>
      expect(client.addAlertPhone).toHaveBeenCalledWith("+5511999999999"),
    );
  });

  it("mostra e edita os dados do usuário na aba Configurações", async () => {
    render(<FinancePage />);
    goToTab("Configurações");
    const section = await billsSection("Dados do usuário");

    expect(await within(section).findByDisplayValue("ada@example.com")).toBeDisabled();
    const nameInput = await within(section).findByDisplayValue("Ada");
    fireEvent.change(nameInput, { target: { value: "Ada Lovelace" } });
    fireEvent.click(within(section).getByText("Salvar"));

    await waitFor(() =>
      expect(client.updateCurrentUser).toHaveBeenCalledWith({ display_name: "Ada Lovelace" }),
    );
  });
});
