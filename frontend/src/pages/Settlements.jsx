import { useEffect, useState } from "react";
import { CheckCircle2, CircleAlert, HandCoins, ShieldCheck, Sparkles, WalletCards } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import { ErrorState, PageSkeleton } from "../components/PageState.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import api, { newIdempotencyKey } from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { StatusBadgeClasses, formatMoney } from "../utils/format";

export default function Settlements() {
  const { groupId } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const [settlements, setSettlements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [payingId, setPayingId] = useState(null);
  const [activePayment, setActivePayment] = useState(null);
  const [manualTarget, setManualTarget] = useState(null); // settlement being recorded as "paid outside SplitPay"
  const [manualBusy, setManualBusy] = useState(false);

  async function refresh() {
    setLoadError("");
    try {
      const res = await api.get(`/groups/${groupId}/settlements`);
      setSettlements(res.data);
    } catch (err) {
      setLoadError(getErrorMessage(err, "Could not load settlements."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId]);

  async function handleGenerate() {
    setLoading(true);
    try {
      await api.post(`/groups/${groupId}/settlements/generate`);
      toast.info("Settlements recalculated from the latest balances.");
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not recalculate settlements."));
    }
    await refresh();
  }

  // A payment that was started earlier (page reloaded mid-payment): pick it back up.
  async function handleResume(settlement) {
    try {
      const { data } = await api.get("/payments");
      const live = data.find((p) => p.settlement_id === settlement.id && p.status === "PENDING");
      if (!live) {
        toast.info("That payment is no longer open. Refreshing…");
        await refresh();
        return;
      }
      setPayingId(settlement.id);
      setActivePayment({ settlementId: settlement.id, payment: live });
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not resume the payment."));
    }
  }

  async function handleRecordManual() {
    if (!manualTarget) return;
    setManualBusy(true);
    try {
      await api.post(
        `/groups/${groupId}/settlements/record`,
        { from_user: manualTarget.from_user, to_user: manualTarget.to_user, amount: manualTarget.amount },
        { headers: { "Idempotency-Key": newIdempotencyKey() } }
      );
      toast.success("Recorded as settled. Balances were updated.");
      setManualTarget(null);
      await refresh();
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not record this settlement."));
      setManualTarget(null);
      await refresh();
    } finally {
      setManualBusy(false);
    }
  }

  async function handlePay(settlement) {
    setPayingId(settlement.id);
    setActivePayment(null);
    try {
      const idempotencyKey = newIdempotencyKey();
      const res = await api.post(
        "/payments/create",
        { settlement_id: settlement.id },
        { headers: { "Idempotency-Key": idempotencyKey } }
      );
      setActivePayment({ settlementId: settlement.id, payment: res.data });
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not start payment."));
      setPayingId(null);
      await refresh();
    }
  }

  async function handleSimulate(payment, outcome) {
    try {
      const res = await api.post("/payments/" + payment.id + "/simulate?outcome=" + outcome);
      setActivePayment((prev) => (prev ? { ...prev, payment: res.data } : null));
      await refresh();
      if (res.data.status === "SUCCESS") {
        toast.success("Payment successful. Balances were updated.");
        setTimeout(() => {
          setPayingId(null);
          setActivePayment(null);
        }, 1500);
      }
    } catch (err) {
      toast.error(getErrorMessage(err, "Could not complete the simulated payment."));
    }
  }

  if (loading) return <PageSkeleton rows={3} className="h-28" />;
  if (loadError) return <ErrorState message={loadError} onRetry={refresh} />;

  return (
    <div className="space-y-6">
      <div className="animate-fade-in flex items-center justify-between gap-3">
        <div>
          <p className="section-label">Settlement</p>
          <h1 className="fintech-header">Settlements</h1>
          <p className="text-sm text-slate-500">Simplified — the fewest payments needed to settle up.</p>
          <Link to={`/groups/${groupId}`} className="mt-1 inline-block text-xs font-semibold text-brand-700 hover:underline">← Back to group</Link>
        </div>
        <button
          onClick={handleGenerate}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
        >
          Recalculate
        </button>
      </div>

      {settlements.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-brand-200 bg-gradient-to-br from-brand-50 via-white to-blue-50 p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700">
            <WalletCards className="h-5 w-5" />
          </div>
          <p className="mt-4 text-base font-bold text-slate-800">No settlements yet</p>
          <p className="mt-1 text-sm text-slate-500">Click “Recalculate” once expenses have been added.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {settlements.map((s) => {
            const isDebtor = s.from_user === user.id;
            const showPayFlow = payingId === s.id && activePayment;

            return (
              <li key={s.id} className="animate-fade-in rounded-2xl border border-blue-100 bg-white p-4 shadow-soft transition-all duration-200 hover:shadow-soft-lg">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-slate-600">
                      {s.from_user === user.id ? "You" : s.from_name || "This member"} owe
                      {s.from_user === user.id ? "" : "s"}{" "}
                      {s.to_user === user.id ? "you" : s.to_name || "this member"}
                    </p>
                    <p className="mt-1 text-2xl font-black tracking-tight text-slate-900">{formatMoney(s.amount)}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={"rounded-full border px-2.5 py-1 text-xs font-semibold " + StatusBadgeClasses(s.status)}>
                      {s.status}
                    </span>
                    {s.method === "MANUAL" && (
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-500">
                        Paid outside SplitPay
                      </span>
                    )}
                    {(isDebtor || s.to_user === user.id) && s.status === "PENDING" && (
                      <button
                        onClick={() => setManualTarget(s)}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
                      >
                        <HandCoins className="h-3.5 w-3.5" />
                        Mark as paid
                      </button>
                    )}
                    {isDebtor && s.status === "PENDING" && (
                      <button
                        onClick={() => handlePay(s)}
                        disabled={payingId === s.id}
                        className="rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow disabled:opacity-60"
                      >
                        {payingId === s.id ? "Starting…" : "Pay Now"}
                      </button>
                    )}
                    {isDebtor && s.status === "PROCESSING" && !showPayFlow && (
                      <button
                        onClick={() => handleResume(s)}
                        className="rounded-xl border border-brand-200 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-100"
                      >
                        Continue payment
                      </button>
                    )}
                  </div>
                </div>

                {showPayFlow && (
                  <div className="mt-4 overflow-hidden rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50 via-white to-blue-50 p-4">
                    {activePayment.payment.status === "SUCCESS" ? (
                      <div className="flex flex-col items-center justify-center py-4 text-center">
                        <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                          <CheckCircle2 className="h-8 w-8" />
                        </div>
                        <p className="text-xl font-black text-emerald-600">Payment successful</p>
                        <p className="mt-2 text-sm text-slate-600">
                          Transaction ID: {activePayment.payment.gateway_payment_id || activePayment.payment.id}
                        </p>
                      </div>
                    ) : activePayment.payment.status === "FAILED" ? (
                      <div className="text-center">
                        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600">
                          <CircleAlert className="h-6 w-6" />
                        </div>
                        <p className="text-lg font-bold text-rose-600">Payment failed</p>
                        <button
                          onClick={() => handlePay(s)}
                          className="mt-3 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white transition-all duration-200 hover:bg-rose-700"
                        >
                          Try again
                        </button>
                      </div>
                    ) : (
                      <div className="text-center">
                        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                          <ShieldCheck className="h-6 w-6" />
                        </div>
                        <p className="text-base font-bold text-slate-800">UPI payment in progress</p>
                        <p className="mt-2 text-sm text-slate-600">
                          Sandbox order <code className="rounded bg-slate-200 px-1.5 py-0.5 text-xs font-medium">{activePayment.payment.gateway_order_id}</code> created.
                          Complete the simulated payment below.
                        </p>
                        <div className="mt-4 flex justify-center gap-2">
                          <button
                            onClick={() => handleSimulate(activePayment.payment, "success")}
                            className="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-all duration-200 hover:bg-emerald-700"
                          >
                            Simulate success
                          </button>
                          <button
                            onClick={() => handleSimulate(activePayment.payment, "failure")}
                            className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-all duration-200 hover:bg-rose-700"
                          >
                            Simulate failure
                          </button>
                        </div>
                        <p className="mt-3 flex items-center justify-center gap-2 text-[11px] text-slate-500">
                          <Sparkles className="h-3.5 w-3.5 text-brand-500" />
                          Payment gateway sandbox — no real money moves.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <ConfirmDialog
        open={!!manualTarget}
        tone="primary"
        busy={manualBusy}
        title="Mark this as paid?"
        message={
          manualTarget
            ? `This records that ${manualTarget.from_user === user.id ? "you paid" : `${manualTarget.from_name || "they"} paid`} ${
                manualTarget.to_user === user.id ? "you" : manualTarget.to_name || "them"
              } ${formatMoney(manualTarget.amount)} outside SplitPay (cash or a direct UPI transfer). Balances update immediately.`
            : ""
        }
        confirmLabel="Yes, mark as paid"
        onConfirm={handleRecordManual}
        onCancel={() => !manualBusy && setManualTarget(null)}
      />
    </div>
  );
}
