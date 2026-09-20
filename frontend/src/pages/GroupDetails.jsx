import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Banknote, Check, LogOut, Pencil, ReceiptText, Trash2, UserPlus, Users, X } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import { ErrorState, PageSkeleton } from "../components/PageState.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatDate, formatMoney } from "../utils/format";

export default function GroupDetails() {
  const { groupId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  const [group, setGroup] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [addEmail, setAddEmail] = useState("");
  const [addError, setAddError] = useState("");
  const [adding, setAdding] = useState(false);

  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [savingName, setSavingName] = useState(false);

  // One dialog at a time: { kind: "group" | "expense" | "member" | "leave", target? }
  const [dialog, setDialog] = useState(null);
  const [dialogBusy, setDialogBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [groupRes, expensesRes] = await Promise.all([
        api.get(`/groups/${groupId}`),
        api.get(`/groups/${groupId}/expenses`),
      ]);
      setGroup(groupRes.data);
      setExpenses(expensesRes.data);
    } catch (err) {
      setLoadError(
        err.response?.status === 404 ? "This group doesn't exist or you're no longer a member." : getErrorMessage(err, "Could not load this group.")
      );
    } finally {
      setLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleAddMember(e) {
    e.preventDefault();
    setAddError("");
    setAdding(true);
    try {
      await api.post(`/groups/${groupId}/members`, { email: addEmail });
      setAddEmail("");
      toast.success("Member added.");
      await refresh();
    } catch (err) {
      setAddError(getErrorMessage(err, "Could not add member."));
    } finally {
      setAdding(false);
    }
  }

  async function handleRename(e) {
    e.preventDefault();
    if (!nameDraft.trim() || nameDraft.trim() === group.name) {
      setRenaming(false);
      return;
    }
    setSavingName(true);
    try {
      await api.patch(`/groups/${groupId}`, { name: nameDraft.trim() });
      toast.success("Group renamed.");
      setRenaming(false);
      await refresh();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not rename the group."));
    } finally {
      setSavingName(false);
    }
  }

  async function runDialogAction() {
    if (!dialog) return;
    setDialogBusy(true);
    try {
      if (dialog.kind === "group") {
        await api.delete(`/groups/${groupId}`);
        toast.success(`“${group.name}” was deleted.`);
        navigate("/groups");
        return;
      }
      if (dialog.kind === "expense") {
        await api.delete(`/expenses/${dialog.target.id}`);
        toast.success("Expense deleted. Balances were updated.");
      } else if (dialog.kind === "member") {
        await api.delete(`/groups/${groupId}/members/${dialog.target.id}`);
        toast.success(`${dialog.target.name} was removed.`);
      } else if (dialog.kind === "leave") {
        await api.delete(`/groups/${groupId}/members/${user.id}`);
        toast.success(`You left “${group.name}”.`);
        navigate("/groups");
        return;
      }
      setDialog(null);
      await refresh();
    } catch (err) {
      toast.error(getErrorMessage(err, "That didn't work. Nothing was changed."));
      setDialog(null);
    } finally {
      setDialogBusy(false);
    }
  }

  if (loading && !group) return <PageSkeleton rows={3} className="h-40" />;
  if (loadError || !group) return <ErrorState message={loadError} onRetry={refresh} />;

  const isCreator = group.created_by === user.id;
  const nameOf = (id) => group.members.find((m) => m.user.id === id)?.user.name || "Someone";

  const dialogCopy = {
    group: {
      title: `Delete “${group.name}”?`,
      message: `This permanently deletes the group, its ${expenses.length} expense${expenses.length === 1 ? "" : "s"} and all settlement history for every member. This can't be undone.`,
      confirmLabel: "Delete group",
    },
    expense: {
      title: "Delete this expense?",
      message: dialog?.target
        ? `“${dialog.target.description}” (${formatMoney(dialog.target.total_amount)}) will be removed and everyone's balances will be recalculated.`
        : "",
      confirmLabel: "Delete expense",
    },
    member: {
      title: `Remove ${dialog?.target?.name}?`,
      message: "They will no longer see this group. You can only remove someone who has no outstanding balance.",
      confirmLabel: "Remove member",
    },
    leave: {
      title: `Leave “${group.name}”?`,
      message: "You'll lose access to this group. You can only leave when you have nothing owed or due.",
      confirmLabel: "Leave group",
    },
  }[dialog?.kind] || {};

  return (
    <div className="space-y-6">
      <div className="animate-fade-in flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="section-label">Group overview</p>
          {renaming ? (
            <form onSubmit={handleRename} className="mt-1 flex items-center gap-2">
              <input
                autoFocus
                value={nameDraft}
                maxLength={150}
                onChange={(e) => setNameDraft(e.target.value)}
                className="w-full min-w-[12rem] rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-lg font-bold text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
              />
              <button disabled={savingName} className="rounded-xl bg-slate-900 p-2.5 text-white hover:bg-slate-700 disabled:opacity-50" aria-label="Save name">
                <Check className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => setRenaming(false)} className="rounded-xl border border-slate-200 bg-white p-2.5 text-slate-500 hover:bg-slate-50" aria-label="Cancel rename">
                <X className="h-4 w-4" />
              </button>
            </form>
          ) : (
            <div className="flex items-center gap-2">
              <h1 className="fintech-header truncate">{group.name}</h1>
              {isCreator && (
                <button
                  onClick={() => {
                    setNameDraft(group.name);
                    setRenaming(true);
                  }}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  aria-label="Rename group"
                >
                  <Pencil className="h-4 w-4" />
                </button>
              )}
            </div>
          )}
          <p className="text-sm text-slate-500">{group.members.length} members</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/groups/${groupId}/settlements`}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
          >
            Settlements
          </Link>
          <Link
            to={`/groups/${groupId}/add-expense`}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow"
          >
            <Banknote className="h-4 w-4" />
            Add Expense
          </Link>
          {isCreator && (
            <button
              onClick={() => setDialog({ kind: "group" })}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-100 bg-white px-4 py-2 text-sm font-semibold text-rose-600 shadow-sm hover:bg-rose-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete group
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-soft lg:col-span-1">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
              <Users className="h-4 w-4" />
            </div>
            <h2 className="text-base font-bold text-slate-800">Members</h2>
          </div>
          <ul className="space-y-2">
            {group.members.map((m) => (
              <li key={m.user.id} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2 text-sm">
                <span className="text-slate-700">
                  {m.user.name} {m.user.id === user.id && <span className="text-slate-400">(you)</span>}
                  {m.user.id === group.created_by && <span className="ml-1.5 text-[10px] font-black uppercase tracking-wider text-slate-400">creator</span>}
                </span>
                {isCreator && m.user.id !== user.id && (
                  <button
                    onClick={() => setDialog({ kind: "member", target: { id: m.user.id, name: m.user.name } })}
                    className="rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                    aria-label={`Remove ${m.user.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
          <form onSubmit={handleAddMember} className="mt-4 space-y-2 border-t border-slate-100 pt-3">
            {addError && <p className="text-xs text-rose-600">{addError}</p>}
            <label className="block text-xs font-medium text-slate-500">Add member by email</label>
            <div className="flex gap-2">
              <input
                required
                type="email"
                value={addEmail}
                onChange={(e) => setAddEmail(e.target.value)}
                placeholder="friend@example.com"
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-2 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
              />
              <button
                type="submit"
                disabled={adding}
                className="inline-flex items-center gap-1 whitespace-nowrap rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition-all duration-200 hover:bg-slate-700 disabled:opacity-60"
              >
                <UserPlus className="h-3.5 w-3.5" />
                {adding ? "Adding…" : "Add"}
              </button>
            </div>
          </form>
          {!isCreator && (
            <button
              onClick={() => setDialog({ kind: "leave" })}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-50"
            >
              <LogOut className="h-3.5 w-3.5" />
              Leave group
            </button>
          )}
        </div>

        <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-soft lg:col-span-2">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
              <ArrowRight className="h-4 w-4" />
            </div>
            <h2 className="text-base font-bold text-slate-800">Balances</h2>
          </div>
          {group.balances.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/70 p-5 text-sm text-emerald-700">
              Everyone is settled up. 🎉
            </p>
          ) : (
            <>
              <ul className="space-y-2">
                {group.balances.map((b) => (
                  <li key={b.user.id} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm">
                    <span className="text-slate-700">
                      {b.user.name} {b.user.id === user.id && <span className="text-slate-400">(you)</span>}
                    </span>
                    <span className={parseFloat(b.net_balance) >= 0 ? "font-bold text-emerald-600" : "font-bold text-rose-600"}>
                      {parseFloat(b.net_balance) >= 0 ? "gets back " : "owes "}
                      {formatMoney(Math.abs(parseFloat(b.net_balance)))}
                    </span>
                  </li>
                ))}
              </ul>
              {group.debts?.length > 0 && (
                <div className="mt-4 border-t border-slate-100 pt-3">
                  <p className="mb-2 text-xs font-medium text-slate-500">Simplest way to settle up</p>
                  <ul className="space-y-1.5">
                    {group.debts.map((d, i) => (
                      <li key={`${d.from_user.id}-${d.to_user.id}-${i}`} className="flex items-center justify-between text-sm text-slate-600">
                        <span>
                          {d.from_user.id === user.id ? "You" : d.from_user.name} pay{d.from_user.id === user.id ? "" : "s"}{" "}
                          {d.to_user.id === user.id ? "you" : d.to_user.name}
                        </span>
                        <span className="font-bold text-slate-900">{formatMoney(d.amount)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-soft">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
            <ReceiptText className="h-4 w-4" />
          </div>
          <h2 className="text-base font-bold text-slate-800">Expenses</h2>
        </div>
        {expenses.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm text-slate-500">
            No expenses yet.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {expenses.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-semibold text-slate-800">{e.description}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    Paid by {e.paid_by_name || nameOf(e.paid_by)} · {formatDate(e.created_at)} · {e.split_type}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <span className="mr-2 font-bold text-slate-900">{formatMoney(e.total_amount)}</span>
                  <Link
                    to={`/groups/${groupId}/expenses/${e.id}/edit`}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    aria-label={`Edit ${e.description}`}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Link>
                  <button
                    onClick={() => setDialog({ kind: "expense", target: e })}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                    aria-label={`Delete ${e.description}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={!!dialog}
        tone="danger"
        busy={dialogBusy}
        title={dialogCopy.title}
        message={dialogCopy.message}
        confirmLabel={dialogCopy.confirmLabel}
        onConfirm={runDialogAction}
        onCancel={() => !dialogBusy && setDialog(null)}
      />
    </div>
  );
}
