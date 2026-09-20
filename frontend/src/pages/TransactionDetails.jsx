import { ArrowLeft, ReceiptText } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorState, PageSkeleton } from "../components/PageState.jsx";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { StatusBadgeClasses, formatDate, formatMoney } from "../utils/format";

export default function TransactionDetails() {
  const { paymentId } = useParams();
  const [tx, setTx] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  function load() {
    setLoading(true); setLoadError("");
    api.get(`/payments/transactions/${paymentId}`)
      .then((res) => setTx(res.data))
      .catch((err) => setLoadError(err.response?.status === 404 ? "Transaction not found." : getErrorMessage(err, "Could not load this transaction.")))
      .finally(() => setLoading(false));
  }
  useEffect(load, [paymentId]);

  if (loading) return <div className="mx-auto max-w-lg"><PageSkeleton rows={1} className="h-72" /></div>;
  if (loadError || !tx) return <div className="mx-auto max-w-lg"><ErrorState message={loadError || "Transaction not found."} onRetry={loadError === "Transaction not found." ? undefined : load} /></div>;

  const rows = [
    ["Transaction ID", "TXN_" + tx.id.slice(0, 8).toUpperCase()],
    ["From", tx.from_user_name],
    ["To", tx.to_user_name],
    ["Amount", formatMoney(tx.amount)],
    ["Status", tx.status],
    ["Date", formatDate(tx.created_at)],
    ["Group", tx.group_name || "—"],
    ["Method", tx.method === "MANUAL" ? "Paid outside SplitPay (recorded manually)" : "UPI (sandbox)"],
    ["Gateway order ID", tx.gateway_order_id || "—"],
    ["Gateway payment ID", tx.gateway_payment_id || "—"],
    ["Settlement ID", tx.settlement_id],
  ];

  return (
    <div className="mx-auto max-w-lg">
      <Link to="/transactions" className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-brand-600 transition-colors hover:text-brand-800">
        <ArrowLeft className="h-4 w-4" />
        Back to transactions
      </Link>
      <div className="overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-soft">
        <div className="bg-gradient-to-r from-brand-600 to-brand-500 p-5 text-white">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15">
                <ReceiptText className="h-5 w-5" />
              </div>
              <h1 className="text-lg font-bold">Transaction details</h1>
            </div>
            <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${StatusBadgeClasses(tx.status)}`}>
              {tx.status}
            </span>
          </div>
        </div>
        <div className="p-5">
          <dl className="divide-y divide-slate-100">
            {rows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3 py-3 text-sm">
                <dt className="text-slate-500">{label}</dt>
                <dd className="text-right font-semibold text-slate-900">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
