import { useEffect, useState } from "react";
import { ArrowRight, Banknote, ReceiptText, UserPlus, Users } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import api from "../services/api";
import { formatDate, formatMoney } from "../utils/format";

export default function GroupDetails() {
  const { groupId } = useParams();
  const { user } = useAuth();
  const [group, setGroup] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addEmail, setAddEmail] = useState("");
  const [addError, setAddError] = useState("");

  async function refresh() {
    setLoading(true);
    const [groupRes, expensesRes] = await Promise.all([
      api.get(`/groups/${groupId}`),
      api.get(`/groups/${groupId}/expenses`),
    ]);
    setGroup(groupRes.data);
    setExpenses(expensesRes.data);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId]);

  async function handleAddMember(e) {
    e.preventDefault();
    setAddError("");
    try {
      await api.post(`/groups/${groupId}/members`, { email: addEmail });
      setAddEmail("");
      refresh();
    } catch (err) {
      setAddError(err.response?.data?.detail || "Could not add member.");
    }
  }

  if (loading || !group) {
    return <p className="text-sm text-slate-400">Loading group...</p>;
  }

  return (
    <div className="space-y-6">
      <div className="animate-fade-in flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="section-label">Group overview</p>
          <h1 className="fintech-header">{group.name}</h1>
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
                </span>
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
                className="inline-flex items-center gap-1 whitespace-nowrap rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition-all duration-200 hover:bg-slate-700"
              >
                <UserPlus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>
          </form>
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
            {expenses.map((e) => {
              const payer = group.members.find((m) => m.user.id === e.paid_by)?.user.name || "Someone";
              return (
                <li key={e.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                  <div>
                    <p className="font-semibold text-slate-800">{e.description}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Paid by {payer} · {formatDate(e.created_at)} · {e.split_type}
                    </p>
                  </div>
                  <span className="font-bold text-slate-900">{formatMoney(e.total_amount)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
