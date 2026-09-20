import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Database,
  LockKeyhole,
  ReceiptText,
  ShieldCheck,
  Sparkles,
  Users,
  WalletCards,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAuth } from "../context/AuthContext.jsx";
import { ErrorState } from "../components/PageState.jsx";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { StatusBadgeClasses, formatDate, formatMoney } from "../utils/format";

export default function Dashboard() {
  const { user } = useAuth();
  const [groups, setGroups] = useState([]);
  const [groupBalances, setGroupBalances] = useState({});
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setLoadError("");
        const groupsRes = await api.get("/groups");
        setGroups(groupsRes.data);
        const balances = {};
        await Promise.all(
          groupsRes.data.map(async (group) => {
            const detail = await api.get(`/groups/${group.id}`);
            const mine = detail.data.balances.find((balance) => balance.user.id === user.id);
            balances[group.id] = mine ? Number(mine.net_balance) : 0;
          })
        );
        setGroupBalances(balances);
        const txRes = await api.get("/payments/transactions/list");
        setTransactions(txRes.data.slice(0, 5));
      } catch (err) {
        setLoadError(getErrorMessage(err, "Could not load your dashboard."));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [user.id, reloadKey]);

  const totalOwed = useMemo(() => Object.values(groupBalances).filter((b) => b > 0).reduce((a, b) => a + b, 0), [groupBalances]);
  const totalOwe = useMemo(() => Object.values(groupBalances).filter((b) => b < 0).reduce((a, b) => a + Math.abs(b), 0), [groupBalances]);
  const netBalance = totalOwed - totalOwe;
  const chartData = groups.map((g) => ({ name: g.name.length > 14 ? `${g.name.slice(0, 14)}…` : g.name, balance: groupBalances[g.id] || 0 }));

  if (loading) return <DashboardSkeleton />;
  if (loadError) return <ErrorState message={loadError} onRetry={() => setReloadKey((k) => k + 1)} />;

  return (
    <div className="space-y-6 pb-8">
      <section className="relative overflow-hidden rounded-[30px] bg-slate-950 p-6 text-white shadow-2xl shadow-slate-950/10 sm:p-8">
        <div className="absolute -right-16 -top-24 h-64 w-64 rounded-full bg-blue-500/25 blur-3xl" />
        <div className="absolute bottom-[-100px] left-1/3 h-60 w-60 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-300">
              <Sparkles className="h-3.5 w-3.5 text-cyan-300" /> Financial overview
            </div>
            <h1 className="max-w-xl text-3xl font-black tracking-[-0.04em] sm:text-4xl">
              Good evening, <span className="text-cyan-300">{user.name.split(" ")[0]}</span>.
            </h1>
            <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
              One place to see who owes you, what you owe, and where your shared spending stands.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <Link to="/groups" className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xs font-black text-slate-950 transition hover:-translate-y-0.5 hover:bg-slate-100">
                <ReceiptText className="h-4 w-4" /> Add an expense
              </Link>
              <Link to="/transactions" className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-white/10">
                View transactions <ChevronRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
          <div className="min-w-[230px] rounded-3xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-xl">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400">Net position</span>
              <WalletCards className="h-4 w-4 text-cyan-300" />
            </div>
            <p className={`mt-3 text-3xl font-black tracking-tight ${netBalance >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{formatMoney(netBalance)}</p>
            <p className="mt-1 text-[11px] text-slate-500">Across {groups.length} active group{groups.length === 1 ? "" : "s"}</p>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MoneyCard label="You are owed" value={totalOwed} icon={<ArrowUpRight />} tone="green" detail="Money coming back to you" />
        <MoneyCard label="You owe" value={totalOwe} icon={<ArrowDownRight />} tone="rose" detail="Your outstanding share" />
        <MoneyCard label="Active groups" value={groups.length} icon={<Users />} tone="blue" detail="Shared spaces you belong to" count />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <p className="eyebrow">Group exposure</p>
              <h2 className="mt-1 text-lg font-black tracking-tight text-slate-950">Balance by group</h2>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1.5 text-[10px] font-black text-emerald-700">
              <CheckCircle2 className="h-3.5 w-3.5" /> Live data
            </span>
          </div>
          {chartData.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chartData} margin={{ left: -18, right: 4, top: 8 }}>
                <CartesianGrid stroke="#eef2f7" vertical={false} strokeDasharray="4 4" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b", fontWeight: 600 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} tickFormatter={(v) => `₹${v}`} />
                <Tooltip
                  cursor={{ fill: "#f8fafc" }}
                  formatter={(value) => [formatMoney(value), "Balance"]}
                  contentStyle={{ borderRadius: 16, border: "1px solid #e2e8f0", boxShadow: "0 18px 40px rgba(15,23,42,.10)" }}
                />
                <Bar dataKey="balance" fill="#0f172a" radius={[8, 8, 3, 3]} maxBarSize={42} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState title="No group data yet" description="Create your first group to start tracking shared expenses." action="Create group" />
          )}
        </div>

        <div className="rounded-3xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-5 shadow-sm sm:p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="eyebrow">Built for reliability</p>
              <h2 className="mt-1 text-lg font-black tracking-tight text-slate-950">Money, handled carefully.</h2>
            </div>
            <ShieldCheck className="h-6 w-6 text-emerald-500" />
          </div>
          <div className="mt-5 space-y-2.5">
            <TrustRow icon={<LockKeyhole />} title="Exact money arithmetic" text="Decimal-based calculations" />
            <TrustRow icon={<Zap />} title="Idempotent payments" text="Retries won't duplicate a transaction" />
            <TrustRow icon={<Database />} title="Cache + database fallback" text="Redis-backed, PostgreSQL-safe reads" />
            <TrustRow icon={<CheckCircle2 />} title="Automated coverage" text="100+ backend tests plus UI tests" />
          </div>
          <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-3.5">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-700"><Clock3 className="h-4 w-4 text-blue-500" /> Consistency is a feature</div>
            <p className="mt-1.5 text-[11px] leading-5 text-slate-400">Signed webhook events and deterministic settlement logic keep retries predictable.</p>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Your groups" eyebrow="Shared spaces" icon={<Users />} href="/groups" linkText="All groups">
          {groups.length ? groups.slice(0, 5).map((group, index) => (
            <Link key={group.id} to={`/groups/${group.id}`} className="group flex items-center justify-between rounded-2xl border border-slate-100 p-3.5 transition hover:border-slate-200 hover:bg-slate-50" style={{ animationDelay: `${index * 40}ms` }}>
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700"><Users className="h-4 w-4" /></div>
                <div className="min-w-0"><p className="truncate text-sm font-bold text-slate-800 group-hover:text-blue-600">{group.name}</p><p className="text-[10px] text-slate-400">Shared expense group</p></div>
              </div>
              <span className={`text-sm font-black ${(groupBalances[group.id] || 0) >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{formatMoney(groupBalances[group.id] || 0)}</span>
            </Link>
          )) : <EmptyState title="No groups yet" description="Start a group for a trip, flat, or dinner." action="Create group" />}
        </Panel>

        <Panel title="Recent activity" eyebrow="Latest payments" icon={<CircleDollarSign />} href="/transactions" linkText="View all">
          {transactions.length ? transactions.map((transaction, index) => (
            <Link key={transaction.id} to={`/transactions/${transaction.id}`} className="group flex items-center justify-between rounded-2xl border border-slate-100 p-3.5 transition hover:border-slate-200 hover:bg-slate-50" style={{ animationDelay: `${index * 40}ms` }}>
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600"><ArrowRight className="h-4 w-4" /></div>
                <div className="min-w-0"><p className="truncate text-sm font-bold text-slate-800">{transaction.from_user_name} <span className="font-normal text-slate-400">paid</span> {transaction.to_user_name}</p><p className="text-[10px] text-slate-400">{formatDate(transaction.created_at)}</p></div>
              </div>
              <div className="text-right"><p className="text-sm font-black text-slate-900">{formatMoney(transaction.amount)}</p><span className={`text-[9px] font-bold uppercase ${StatusBadgeClasses(transaction.status).split(" ").slice(-1)[0]}`}>{transaction.status}</span></div>
            </Link>
          )) : <EmptyState title="No transactions yet" description="Settlements will appear here automatically." />}
        </Panel>
      </section>
    </div>
  );
}

function MoneyCard({ label, value, icon, tone, detail, count = false }) {
  const tones = {
    green: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    rose: "bg-rose-50 text-rose-700 ring-rose-100",
    blue: "bg-blue-50 text-blue-700 ring-blue-100",
  };
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-start justify-between">
        <span className="eyebrow">{label}</span>
        <span className={`flex h-9 w-9 items-center justify-center rounded-xl ring-1 ${tones[tone]}`}>{icon}</span>
      </div>
      <p className="mt-5 text-2xl font-black tracking-tight text-slate-950">{count ? value : formatMoney(value)}</p>
      <p className="mt-1 text-[11px] font-medium text-slate-400">{detail}</p>
    </div>
  );
}

function TrustRow({ icon, title, text }) {
  return <div className="flex items-center gap-3 rounded-2xl border border-slate-100 bg-white p-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white">{icon}</span><div><p className="text-xs font-bold text-slate-800">{title}</p><p className="text-[10px] text-slate-400">{text}</p></div></div>;
}

function Panel({ title, eyebrow, icon, href, linkText, children }) {
  return <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><div className="mb-4 flex items-center justify-between"><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-700">{icon}</div><div><p className="eyebrow">{eyebrow}</p><h2 className="text-base font-black text-slate-950">{title}</h2></div></div>{href && <Link to={href} className="inline-flex items-center gap-1 text-[11px] font-black text-blue-600 hover:text-blue-700">{linkText}<ChevronRight className="h-3.5 w-3.5" /></Link>}</div><div className="space-y-2">{children}</div></div>;
}

function EmptyState({ title, description, action }) {
  return <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-7 text-center"><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-white text-slate-400 shadow-sm"><ReceiptText className="h-4 w-4" /></div><p className="mt-3 text-sm font-bold text-slate-700">{title}</p><p className="mx-auto mt-1 max-w-xs text-[11px] leading-5 text-slate-400">{description}</p>{action && <Link to="/groups" className="mt-4 inline-flex rounded-xl bg-slate-950 px-3.5 py-2 text-[11px] font-bold text-white">{action}</Link>}</div>;
}

function DashboardSkeleton() {
  return <div className="space-y-5 pb-8"><div className="skeleton h-72 rounded-[30px]" /><div className="grid gap-3 sm:grid-cols-3"><div className="skeleton h-32 rounded-3xl" /><div className="skeleton h-32 rounded-3xl" /><div className="skeleton h-32 rounded-3xl" /></div><div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]"><div className="skeleton h-80 rounded-3xl" /><div className="skeleton h-80 rounded-3xl" /></div></div>;
}
