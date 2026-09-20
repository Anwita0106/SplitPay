import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ArrowRightLeft, CheckCircle2, Clock3, ReceiptText, Search, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { ErrorState } from "../components/PageState.jsx";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { StatusBadgeClasses, formatDate, formatMoney } from "../utils/format";

export default function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [loadError, setLoadError] = useState("");

  function load() {
    setLoading(true); setLoadError("");
    api.get("/payments/transactions/list")
      .then((res) => setTransactions(res.data))
      .catch((err) => setLoadError(getErrorMessage(err, "Could not load your transactions.")))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);
  const filtered = useMemo(() => transactions.filter((t) => `${t.from_user_name} ${t.to_user_name} ${t.group_name || ""} ${t.id} ${t.status}`.toLowerCase().includes(query.toLowerCase())), [transactions, query]);
  const completed = transactions.filter((t) => t.status?.toLowerCase() === "completed" || t.status?.toLowerCase() === "success").length;

  return <div className="space-y-6 pb-8">
    <section className="flex flex-col gap-5 rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-end sm:justify-between sm:p-8"><div><span className="eyebrow">Payment ledger</span><h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">Transactions</h1><p className="mt-2 text-sm text-slate-500">A clean audit trail for settlement activity across your groups.</p></div><div className="flex gap-2"><Stat icon={<ReceiptText />} label="Total" value={transactions.length}/><Stat icon={<CheckCircle2 />} label="Completed" value={completed}/></div></section>
    <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3.5 py-3 shadow-sm"><Search className="h-4 w-4 text-slate-400"/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search people, group, transaction ID, or status" className="w-full bg-transparent text-xs font-medium text-slate-700 placeholder:text-slate-400 focus:outline-none" />{query && <button onClick={()=>setQuery("")} className="text-slate-400 hover:text-slate-700"><XCircle className="h-4 w-4"/></button>}</div>
    {loadError ? <ErrorState message={loadError} onRetry={load} /> : loading ? <div className="space-y-2">{[1,2,3,4].map((i)=><div key={i} className="skeleton h-20 rounded-2xl"/>)}</div> : filtered.length === 0 ? <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500"><ReceiptText /></div><p className="mt-4 text-base font-black text-slate-800">{transactions.length === 0 ? "No transactions yet" : "No matching transactions"}</p><p className="mt-1 text-sm text-slate-400">{transactions.length === 0 ? "Payments and settlements you make will show up here." : "Try a different search."}</p></div> : <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"><div className="hidden grid-cols-[1.4fr_1fr_1fr_.8fr_.8fr] gap-4 border-b border-slate-100 bg-slate-50 px-5 py-3 text-[9px] font-black uppercase tracking-[0.15em] text-slate-400 md:grid"><span>Transaction</span><span>From</span><span>To</span><span>Amount</span><span>Status</span></div><div className="divide-y divide-slate-100">{filtered.map((t, i)=><Link key={t.id} to={`/transactions/${t.id}`} className="grid grid-cols-1 gap-3 px-4 py-4 transition hover:bg-slate-50 md:grid-cols-[1.4fr_1fr_1fr_.8fr_.8fr] md:items-center md:gap-4 md:px-5" style={{animationDelay:`${i*25}ms`}}>
      <div className="flex items-center gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600"><ArrowRightLeft className="h-4 w-4"/></div><div className="min-w-0"><p className="truncate font-mono text-[10px] font-black text-blue-600">TXN_{t.id.slice(0,8).toUpperCase()}</p><p className="mt-0.5 text-[10px] text-slate-400">{formatDate(t.created_at)}{t.group_name ? ` · ${t.group_name}` : ""}{t.method === "MANUAL" ? " · paid outside SplitPay" : ""}</p></div></div>
      <div className="flex justify-between gap-3 md:block"><span className="text-[9px] font-black uppercase text-slate-400 md:hidden">From</span><span className="text-xs font-semibold text-slate-700">{t.from_user_name}</span></div>
      <div className="flex justify-between gap-3 md:block"><span className="text-[9px] font-black uppercase text-slate-400 md:hidden">To</span><span className="text-xs font-semibold text-slate-700">{t.to_user_name}</span></div>
      <div className="flex justify-between gap-3 md:block"><span className="text-[9px] font-black uppercase text-slate-400 md:hidden">Amount</span><span className="text-sm font-black text-slate-950">{formatMoney(t.amount)}</span></div>
      <div className="flex justify-between gap-3 md:block"><span className="text-[9px] font-black uppercase text-slate-400 md:hidden">Status</span><span className={`inline-flex rounded-full border px-2 py-1 text-[9px] font-black ${StatusBadgeClasses(t.status)}`}>{t.status}</span></div>
    </Link>)}</div></div>}
    <p className="flex items-center justify-center gap-1.5 text-center text-[10px] text-slate-400"><Clock3 className="h-3 w-3"/> Payment history is read from your settlement ledger.</p>
  </div>;
}
function Stat({icon,label,value}) { return <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2"><div className="flex items-center gap-1.5 text-slate-400">{icon}<span className="text-[9px] font-black uppercase tracking-wider">{label}</span></div><p className="mt-1 text-lg font-black text-slate-900">{value}</p></div>; }
