import { Crown, ShieldCheck, Trash2, UserMinus, Users } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import type { Group, User } from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { useMe } from "../../auth/MeContext";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { Select } from "../../components/ui/Select";
import { useAsync } from "../../lib/useAsync";

/**
 * Admin console (T2.6): manage user roles and user groups. Members of a group
 * share the group owner's ("titular") Finance data.
 */
export function AdminPage() {
  const { user: me, status } = useMe();
  if (status === "loading" || status === "idle") {
    return <p className="text-sm text-gray-500">Carregando…</p>;
  }
  if (me?.role !== "admin") {
    return (
      <Section title="Usuários e grupos" icon={Users}>
        <p className="text-sm text-gray-600">Acesso restrito a administradores.</p>
      </Section>
    );
  }
  return <AdminConsole me={me} />;
}

function AdminConsole({ me }: { me: User }) {
  const client = useApiClient();
  const users = useAsync(() => client.adminListUsers(), [client]);
  const groups = useAsync(() => client.adminListGroups(), [client]);
  const [error, setError] = useState<string | null>(null);

  const allUsers = users.data ?? [];
  const ungrouped = allUsers.filter((u) => u.household_id === null);
  const groupName = new Map((groups.data ?? []).map((g) => [g.household_id, g.name]));

  /** Run an admin action, then reload both lists; show `failure` on error. */
  async function act(action: () => Promise<unknown>, failure: string) {
    setError(null);
    try {
      await action();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(status === 409 ? `${failure} ${conflictHint(err)}` : failure);
    }
    await Promise.all([users.run(), groups.run()]);
  }

  return (
    <div>
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">Usuários e grupos</h1>
      <p className="mb-6 text-sm text-gray-500">
        Administre os papéis dos usuários e os grupos. Os membros de um grupo acessam o mesmo
        conteúdo de Finanças — o do titular do grupo.
      </p>
      {error && (
        <div className="mb-4">
          <ErrorText>{error}</ErrorText>
        </div>
      )}

      <Section title="Grupos" icon={Users}>
        <CreateGroupForm
          candidates={ungrouped}
          onCreate={(name, ownerId) =>
            act(() => client.adminCreateGroup(name, ownerId), "Não foi possível criar o grupo.")
          }
        />
        {groups.status === "error" && <ErrorText>Não foi possível carregar os grupos.</ErrorText>}
        {groups.status === "ready" && (groups.data ?? []).length === 0 && (
          <p className="text-sm text-gray-500">Nenhum grupo criado ainda.</p>
        )}
        <div className="flex flex-col gap-4">
          {(groups.data ?? []).map((group) => (
            <GroupCard
              key={group.household_id}
              group={group}
              candidates={ungrouped}
              client={client}
              act={act}
            />
          ))}
        </div>
      </Section>

      <Section title="Usuários" icon={ShieldCheck}>
        {users.status === "loading" && <p className="text-sm text-gray-500">Carregando…</p>}
        {users.status === "error" && <ErrorText>Não foi possível carregar os usuários.</ErrorText>}
        <ul className="flex flex-col gap-2">
          {allUsers.map((user) => {
            const isAdmin = user.role === "admin";
            return (
              <li
                key={user.user_id}
                className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded border border-gray-200 px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <span className="font-medium">{user.display_name}</span>
                  {user.user_id === me.user_id && <span className="text-gray-500"> (você)</span>}
                  <span className="block truncate text-gray-500">{user.email}</span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
                    {user.household_id ? (groupName.get(user.household_id) ?? "Grupo") : "Sem grupo"}
                  </span>
                  <span
                    className={
                      "rounded px-2 py-0.5 text-xs " +
                      (isAdmin ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-700")
                    }
                  >
                    {isAdmin ? "Admin" : "Membro"}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      act(
                        () => client.adminSetRole(user.user_id, isAdmin ? "member" : "admin"),
                        "Não foi possível alterar o papel.",
                      )
                    }
                    className="text-sm text-blue-600 hover:underline"
                  >
                    {isAdmin ? "Remover admin" : "Tornar admin"}
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      </Section>
    </div>
  );
}

function conflictHint(err: unknown): string {
  const message = err instanceof Error ? err.message : "";
  if (message.includes("last admin")) return "Deve existir ao menos um administrador.";
  if (message.includes("already belongs")) return "O usuário já pertence a um grupo.";
  if (message.includes("owner cannot be removed"))
    return "Troque o titular ou exclua o grupo antes de remover o titular.";
  if (message.includes("new owner")) return "O novo titular precisa ser membro do grupo.";
  return "";
}

function CreateGroupForm({
  candidates,
  onCreate,
}: {
  candidates: User[];
  onCreate: (name: string, ownerId: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [ownerId, setOwnerId] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ownerId) return;
    await onCreate(name.trim(), ownerId);
    setName("");
    setOwnerId("");
  }

  return (
    <form onSubmit={submit} className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end">
      <Field label="Nome do grupo">
        <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Titular (dono dos dados de Finanças)">
        <Select value={ownerId} onChange={(e) => setOwnerId(e.target.value)} required>
          <option value="">Selecione…</option>
          {candidates.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.display_name} ({u.email})
            </option>
          ))}
        </Select>
      </Field>
      <Button type="submit">Criar grupo</Button>
    </form>
  );
}

function GroupCard({
  group,
  candidates,
  client,
  act,
}: {
  group: Group;
  candidates: User[];
  client: ApiClient;
  act: (action: () => Promise<unknown>, failure: string) => Promise<void>;
}) {
  const [name, setName] = useState(group.name);
  const [newMember, setNewMember] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const id = group.household_id;

  return (
    <article
      aria-label={`Grupo ${group.name}`}
      className="rounded-lg border border-gray-200 p-3 sm:p-4"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void act(() => client.adminUpdateGroup(id, { name: name.trim() }), "Não foi possível renomear o grupo.");
        }}
        className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end"
      >
        <Field label="Nome">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Button type="submit" disabled={name.trim() === group.name || !name.trim()}>
          Renomear
        </Button>
      </form>

      <ul className="mb-3 flex flex-col gap-1">
        {group.members.map((member) => {
          const isOwner = member.user_id === group.owner_user_id;
          return (
            <li
              key={member.user_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded bg-gray-50 px-3 py-2 text-sm"
            >
              <span className="flex min-w-0 items-center gap-2">
                {isOwner && <Crown className="h-4 w-4 shrink-0 text-amber-500" aria-hidden />}
                <span className="truncate">
                  {member.display_name} <span className="text-gray-500">· {member.email}</span>
                </span>
                {isOwner && (
                  <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                    Titular
                  </span>
                )}
              </span>
              {!isOwner && (
                <span className="flex gap-3">
                  <button
                    type="button"
                    onClick={() =>
                      act(
                        () => client.adminUpdateGroup(id, { owner_user_id: member.user_id }),
                        "Não foi possível trocar o titular.",
                      )
                    }
                    className="text-sm text-blue-600 hover:underline"
                  >
                    Tornar titular
                  </button>
                  <button
                    type="button"
                    aria-label={`Remover ${member.display_name}`}
                    onClick={() =>
                      act(
                        () => client.adminRemoveMember(id, member.user_id),
                        "Não foi possível remover o membro.",
                      )
                    }
                    className="flex items-center gap-1 text-sm text-red-600 hover:underline"
                  >
                    <UserMinus className="h-4 w-4" aria-hidden />
                    Remover
                  </button>
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!newMember) return;
            void act(
              () => client.adminAddMember(id, newMember),
              "Não foi possível adicionar o membro.",
            ).then(() => setNewMember(""));
          }}
          className="flex flex-col gap-2 sm:flex-row sm:items-end"
        >
          <Field label="Adicionar membro">
            <Select value={newMember} onChange={(e) => setNewMember(e.target.value)}>
              <option value="">Selecione…</option>
              {candidates.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.display_name} ({u.email})
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" disabled={!newMember}>
            Adicionar
          </Button>
        </form>
        {confirmDelete ? (
          <span className="flex items-center gap-3 text-sm">
            <span className="text-gray-600">Excluir o grupo?</span>
            <button
              type="button"
              onClick={() => act(() => client.adminDeleteGroup(id), "Não foi possível excluir o grupo.")}
              className="font-medium text-red-600 hover:underline"
            >
              Confirmar exclusão
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              className="text-gray-600 hover:underline"
            >
              Cancelar
            </button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1 self-start text-sm text-red-600 hover:underline sm:self-auto"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
            Excluir grupo
          </button>
        )}
      </div>
    </article>
  );
}
