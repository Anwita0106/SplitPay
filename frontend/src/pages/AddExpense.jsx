import { useEffect, useState } from "react";
import { Banknote, Percent, ReceiptText, WalletCards } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { ErrorState, PageSkeleton } from "../components/PageState.jsx";
import { useToast } from "../context/ToastContext.jsx";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";

export default function AddExpense() {
  const { groupId, expenseId } = useParams(); // expenseId is set on the edit route
  const isEdit = Boolean(expenseId);
  const navigate = useNavigate();
  const toast = useToast();

  const [members, setMembers] = useState([]);
  const [description, setDescription] = useState("");
  const [totalAmount, setTotalAmount] = useState("");
  const [paidBy, setPaidBy] = useState("");
  const [splitType, setSplitType] = useState("EQUAL");
  const [participantIds, setParticipantIds] = useState([]);
  const [percentages, setPercentages] = useState({});
  const [exactAmounts, setExactAmounts] = useState({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  async function load() {
    setLoading(true);
    setLoadError("");
    try {
      const groupRes = await api.get(`/groups/${groupId}`);
      const m = groupRes.data.members.map((x) => x.user);
      setMembers(m);
      if (!isEdit) {
        setParticipantIds(m.map((u) => u.id));
        setPaidBy(m[0]?.id || "");
        return;
      }
      // Edit mode: prefill every field from the saved expense.
      const { data: e } = await api.get(`/expenses/${expenseId}`);
      setDescription(e.description);
      setTotalAmount(String(e.total_amount));
      setPaidBy(e.paid_by);
      setSplitType(e.split_type);
      setParticipantIds(e.splits.map((x) => x.user_id));
      setPercentages(Object.fromEntries(e.splits.filter((x) => x.percentage != null).map((x) => [x.user_id, String(x.percentage)])));
      setExactAmounts(Object.fromEntries(e.splits.map((x) => [x.user_id, String(x.amount)])));
    } catch (err) {
      setLoadError(getErrorMessage(err, "Could not load this expense."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, expenseId]);

  function toggleParticipant(userId) {
    setParticipantIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  }

  const percentageTotal = Object.values(percentages).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);
  const exactTotal = Object.values(exactAmounts).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      const payload = {
        group_id: groupId,
        description,
        total_amount: totalAmount,
        split_type: splitType,
        paid_by: paidBy,
      };

      if (splitType === "EQUAL") {
        payload.participant_ids = participantIds;
      } else if (splitType === "PERCENTAGE") {
        payload.splits = members
          .filter((m) => percentages[m.id])
          .map((m) => ({ user_id: m.id, percentage: percentages[m.id] }));
      } else if (splitType === "EXACT") {
        payload.splits = members
          .filter((m) => exactAmounts[m.id])
          .map((m) => ({ user_id: m.id, amount: exactAmounts[m.id] }));
      }

      if (isEdit) {
        delete payload.group_id; // the group of an expense can't change
        await api.put(`/expenses/${expenseId}`, payload);
        toast.success("Expense updated. Balances were recalculated.");
      } else {
        await api.post("/expenses", payload);
        toast.success("Expense added.");
      }
      navigate(`/groups/${groupId}`);
    } catch (err) {
      setError(getErrorMessage(err, isEdit ? "Could not save changes." : "Could not add expense."));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="mx-auto max-w-lg"><PageSkeleton rows={2} className="h-48" /></div>;
  if (loadError) return <div className="mx-auto max-w-lg"><ErrorState message={loadError} onRetry={load} /></div>;

  const noParticipants = splitType === "EQUAL" && participantIds.length === 0;

  return (
    <div className="mx-auto max-w-lg">
      <div className="mb-5 animate-fade-in">
        <p className="section-label">{isEdit ? "Edit expense" : "Add expense"}</p>
        <h1 className="fintech-header">{isEdit ? "Edit bill" : "New bill"}</h1>
      </div>
      <form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border border-blue-100 bg-white p-5 shadow-soft">
        {error && <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Description</label>
          <div className="relative">
            <ReceiptText className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              required
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Hotel"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Total amount (₹)</label>
          <div className="relative">
            <WalletCards className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              required
              type="number"
              step="0.01"
              min="0.01"
              value={totalAmount}
              onChange={(e) => setTotalAmount(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Paid by</label>
          <select
            value={paidBy}
            onChange={(e) => setPaidBy(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
          >
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Split type</label>
          <div className="flex gap-2">
            {["EQUAL", "PERCENTAGE", "EXACT"].map((t) => (
              <button
                type="button"
                key={t}
                onClick={() => setSplitType(t)}
                className={`rounded-xl border px-3 py-2 text-xs font-semibold ${
                  splitType === t
                    ? "border-brand-500 bg-brand-50 text-brand-700 shadow-sm"
                    : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {splitType === "EQUAL" && (
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Split between</label>
            <div className="space-y-2">
              {members.map((m) => (
                <label key={m.id} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={participantIds.includes(m.id)}
                    onChange={() => toggleParticipant(m.id)}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  {m.name}
                </label>
              ))}
            </div>
          </div>
        )}

        {splitType === "PERCENTAGE" && (
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">
              Percentages <span className={percentageTotal === 100 ? "text-emerald-600" : "text-slate-400"}>(total: {percentageTotal}%)</span>
            </label>
            <div className="space-y-2">
              {members.map((m) => (
                <div key={m.id} className="flex items-center gap-2">
                  <span className="w-28 shrink-0 text-sm text-slate-700">{m.name}</span>
                  <div className="relative w-full">
                    <Percent className="pointer-events-none absolute left-3 top-3 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      max="100"
                      value={percentages[m.id] || ""}
                      onChange={(e) => setPercentages((p) => ({ ...p, [m.id]: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2 pl-8 pr-3 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {splitType === "EXACT" && (
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">
              Exact amounts <span className={exactTotal === parseFloat(totalAmount || 0) ? "text-emerald-600" : "text-slate-400"}>(total: ₹{exactTotal.toFixed(2)})</span>
            </label>
            <div className="space-y-2">
              {members.map((m) => (
                <div key={m.id} className="flex items-center gap-2">
                  <span className="w-28 shrink-0 text-sm text-slate-700">{m.name}</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={exactAmounts[m.id] || ""}
                    onChange={(e) => setExactAmounts((p) => ({ ...p, [m.id]: e.target.value }))}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {noParticipants && <p className="text-xs text-rose-600">Select at least one person to split this between.</p>}

        <button
          type="submit"
          disabled={submitting || noParticipants}
          className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-3 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow disabled:opacity-60"
        >
          {submitting ? (isEdit ? "Saving..." : "Adding...") : isEdit ? "Save changes" : "Add expense"}
        </button>
      </form>
    </div>
  );
}
