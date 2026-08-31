import { useEffect, useState } from "react";
import { ArrowRightLeft, ReceiptText } from "lucide-react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { StatusBadgeClasses, formatDate, formatMoney } from "../utils/format";

export default function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/payments/transactions/list").then((res) => {
      setTransactions(res.data);
      setLoading(false);
    });
  }, []);

  return (
    <div className="space-y-4">
      <div className="animate-fade-in">
        <p className="section-label">Activity</p>
        <h1 className="fintech-header">Transactions</h1>
        <p className="text-sm text-slate-500">Every payment attempt across your groups.</p>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton h-14 rounded-2xl" />
          ))}
        </div>
      ) : transactions.length === 0 ? (
        <div className="animate-fade-in rounded-2xl border border-dashed border-brand-200 bg-gradient-to-br from-brand-50 via-white to-blue-50 p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700">
            <ReceiptText className="h-5 w-5" />
          </div>
          <p className="mt-4 text-lg font-bold text-slate-800">No transactions yet</p>
          <p className="mt-1 text-sm text-slate-500">Your payment history will appear here once a settlement is triggered.</p>
        </div>
      ) : (
        <div className="animate-fade-in overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-soft">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-blue-100 bg-gradient-to-r from-brand-50 to-blue-50 text-xs uppercase tracking-[0.12em] text-slate-500">
              <tr>
                <th className="px-4 py-3">Transaction ID</th>
                <th className="px-4 py-3">From</th>
                <th className="px-4 py-3">To</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-blue-50">
              {transactions.map((t, i) => (
                <tr
                  key={t.id}
                  className="animate-fade-in transition-colors duration-150 hover:bg-blue-50/60"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <td className="px-4 py-3">
                    <Link
                      to={`/transactions/${t.id}`}
                      className="inline-flex items-center gap-2 font-mono text-xs font-semibold text-brand-600 transition-colors hover:text-brand-800"
                    >
                      <ArrowRightLeft className="h-3.5 w-3.5" />
                      TXN_{t.id.slice(0, 8).toUpperCase()}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{t.from_user_name}</td>
                  <td className="px-4 py-3 text-slate-700">{t.to_user_name}</td>
                  <td className="px-4 py-3 font-bold text-slate-900">{formatMoney(t.amount)}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${StatusBadgeClasses(t.status)}`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{formatDate(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
