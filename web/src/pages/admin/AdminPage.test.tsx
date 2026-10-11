import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Group, User } from "../../api/types";

const client = vi.hoisted(() => ({
  adminListUsers: vi.fn(),
  adminListGroups: vi.fn(),
  adminSetRole: vi.fn(),
  adminCreateGroup: vi.fn(),
  adminUpdateGroup: vi.fn(),
  adminDeleteGroup: vi.fn(),
  adminAddMember: vi.fn(),
  adminRemoveMember: vi.fn(),
}));
const me = vi.hoisted(() => ({ value: { user: null as unknown, status: "ready" } }));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));
vi.mock("../../auth/MeContext", () => ({ useMe: () => me.value }));

import { AdminPage } from "./AdminPage";

function user(id: string, name: string, extra: Partial<User> = {}): User {
  return {
    user_id: id,
    email: `${id}@example.com`,
    display_name: name,
    status: "active",
    role: "member",
    household_id: null,
    created_at: "2026-10-01T00:00:00Z",
    ...extra,
  };
}

const ADMIN = user("root", "Root", { role: "admin" });
const OWNER = user("owner", "Olga", { household_id: "g1" });
const MEMBER = user("member", "Miro", { household_id: "g1" });
const LONER = user("loner", "Lia");
const GROUP: Group = {
  household_id: "g1",
  name: "Família",
  owner_user_id: "owner",
  created_at: "2026-10-01T00:00:00Z",
  members: [
    { user_id: "member", display_name: "Miro", email: "member@example.com" },
    { user_id: "owner", display_name: "Olga", email: "owner@example.com" },
  ],
};

describe("AdminPage", () => {
  beforeEach(() => {
    me.value = { user: ADMIN, status: "ready" };
    Object.values(client).forEach((fn) => fn.mockReset());
    client.adminListUsers.mockResolvedValue([ADMIN, OWNER, MEMBER, LONER]);
    client.adminListGroups.mockResolvedValue([GROUP]);
    client.adminSetRole.mockResolvedValue(ADMIN);
    client.adminCreateGroup.mockResolvedValue(GROUP);
    client.adminUpdateGroup.mockResolvedValue(GROUP);
    client.adminDeleteGroup.mockResolvedValue(undefined);
    client.adminAddMember.mockResolvedValue(GROUP);
    client.adminRemoveMember.mockResolvedValue(undefined);
  });

  it("is restricted to admins", () => {
    me.value = { user: LONER, status: "ready" };
    render(<AdminPage />);
    expect(screen.getByText("Acesso restrito a administradores.")).toBeInTheDocument();
    expect(client.adminListUsers).not.toHaveBeenCalled();
  });

  it("lists groups with their owner and users with their roles", async () => {
    render(<AdminPage />);
    const card = await screen.findByRole("article", { name: "Grupo Família" });
    expect(within(card).getByText("Titular")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Remover Miro" })).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Remover Olga" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
  });

  it("creates a group with an ungrouped owner", async () => {
    render(<AdminPage />);
    await screen.findByRole("article", { name: "Grupo Família" });
    fireEvent.change(screen.getByLabelText("Nome do grupo"), { target: { value: "Casa" } });
    fireEvent.change(screen.getByLabelText(/Titular/), { target: { value: "loner" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar grupo" }));
    await waitFor(() => expect(client.adminCreateGroup).toHaveBeenCalledWith("Casa", "loner"));
  });

  it("adds, removes and promotes members, and deletes after confirmation", async () => {
    render(<AdminPage />);
    const card = await screen.findByRole("article", { name: "Grupo Família" });

    fireEvent.change(within(card).getByLabelText("Adicionar membro"), { target: { value: "loner" } });
    fireEvent.click(within(card).getByRole("button", { name: "Adicionar" }));
    await waitFor(() => expect(client.adminAddMember).toHaveBeenCalledWith("g1", "loner"));

    fireEvent.click(within(card).getByRole("button", { name: "Remover Miro" }));
    await waitFor(() => expect(client.adminRemoveMember).toHaveBeenCalledWith("g1", "member"));

    fireEvent.click(within(card).getByRole("button", { name: "Tornar titular" }));
    await waitFor(() =>
      expect(client.adminUpdateGroup).toHaveBeenCalledWith("g1", { owner_user_id: "member" }),
    );

    fireEvent.click(within(card).getByRole("button", { name: "Excluir grupo" }));
    expect(client.adminDeleteGroup).not.toHaveBeenCalled();
    fireEvent.click(within(card).getByRole("button", { name: "Confirmar exclusão" }));
    await waitFor(() => expect(client.adminDeleteGroup).toHaveBeenCalledWith("g1"));
  });

  it("toggles a user's admin role and explains a last-admin conflict", async () => {
    client.adminSetRole.mockRejectedValue(
      Object.assign(new Error("cannot demote the last admin"), { status: 409 }),
    );
    render(<AdminPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Remover admin" }));
    await waitFor(() => expect(client.adminSetRole).toHaveBeenCalledWith("root", "member"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Deve existir ao menos um administrador.",
    );
  });
});
