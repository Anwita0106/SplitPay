import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, CircleDollarSign, CreditCard, Landmark, Sparkles, TrendingUp, Users, Wallet2 } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAuth } from "../context/AuthContext.jsx";
import api from "../services/api";
import { StatusBadgeClasses, formatDate, formatMoney } from "../utils/format";

export default function Dashboard() {
  const { user } = useAuth();
  const [groups, setGroups] = useState([]);
  const [groupBalances, setGroupBalances] = useState({});
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const groupsRes = await api.get("/groups");
      setGroups(groupsRes.data);

      const balances = {};
      await Promise.all(
        groupsRes.data.map(async (g) => {
          const detail = await api.get(`/groups/${g.id}`);
          const mine = detail.data.balances.find((b) => b.user.id === user.id);
          balances[g.id] = mine ? parseFloat(mine.net_balance) : 0;
        })
      );
      setGroupBalances(balances);

      const txRes = await api.get("/payments/transactions/list");
      setTransactions(txRes.data.slice(0, 5));

      setLoading(false);
    }
    load();
  }, [user.id]);

  const totalOwedToMe = Object.values(groupBalances)
    .filter((b) => b > 0)
    .reduce((a, b) => a + b, 0);
  const totalIOwe = Object.values(groupBalances)
    .filter((b) => b < 0)
    .reduce((a, b) => a + Math.abs(b), 0);

  const chartData = groups.map((g) => ({
    name: g.name.length > 12 ? g.name.slice(0, 12) + "…" : g.name,
    balance: groupBalances[g.id] || 0,
  }));

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="skeleton h-32 w-full rounded-[28px]" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="skeleton h-28 rounded-2xl" />
          <div className="skeleton h-28 rounded-2xl" />
          <div className="skeleton h-28 rounded-2xl" />
        </div>
        <div className="skeleton h-64 rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="animate-fade-in overflow-hidden rounded-[28px] border border-brand-200/80 bg-gradient-to-br from-brand-700 via-brand-600 to-sky-500 p-5 text-white shadow-soft-lg">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-blue-100">
              <Sparkles className="h-3.5 w-3.5" />
              Smart balance
            </div>
            <h1 className="mt-4 text-2xl font-black tracking-tight sm:text-3xl">
              Welcome back, <span className="text-blue-100">{user.name.split(" ")[0]}</span>
            </h1>
            <p className="mt-2 max-w-md text-sm text-blue-100/90">
              Here&apos;s where things stand across your groups and recent UPI settlements.
            </p>
          </div>
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10 shadow-inner backdrop-blur-sm ring-1 ring-white/20">
            <Wallet2 className="h-8 w-8 text-blue-50" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="You are owed"
          value={formatMoney(totalOwedToMe)}
          tone="emerald"
          delay="0ms"
          icon={<ArrowUpRight className="h-5 w-5" />}
        />
        <StatCard
          label="You owe"
          value={formatMoney(totalIOwe)}
          tone="rose"
          delay="60ms"
          icon={<ArrowRight className="h-5 w-5" />}
        />
        <StatCard
          label="Active groups"
          value={groups.length}
          tone="brand"
          delay="120ms"
          icon={<Users className="h-5 w-5" />}
        />
      </div>

      {chartData.length > 0 && (
        <div className="animate-fade-in rounded-2xl border border-blue-100 bg-white p-4 shadow-soft transition-all duration-300 hover:shadow-soft-lg">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="section-label">Insights</p>
              <h2 className="mt-1 text-base font-bold text-slate-800">Balance by group</h2>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700">
              <TrendingUp className="h-3.5 w-3.5" />
              Updated now
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData}>
              <defs>
                <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#60a5fa" stopOpacity={1} />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity={0.92} />
                </linearGradient>
                <linearGradient id="barFillWarm" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#fdba74" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="#f97316" stopOpacity={0.9} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#dfe7ff" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#475569" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: "#475569" }} axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(v) => formatMoney(v)}
                contentStyle={{ borderRadius: 16, borderColor: "#bfdbfe", boxShadow: "0 12px 30px rgba(37, 99, 235, 0.14)" }}
              />
              <Bar dataKey="balance" fill="url(#barFill)" radius={[8, 8, 0, 0]} animationDuration={700} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="animate-fade-in rounded-2xl border border-blue-100 bg-white p-4 shadow-soft transition-all duration-300 hover:-translate-y-0.5 hover:shadow-soft-lg">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 text-brand-700">
                <Landmark className="h-4 w-4" />
              </div>
              <h2 className="text-base font-bold text-slate-800">Your groups</h2>
            </div>
            <Link to="/groups" className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 transition-colors hover:text-brand-800">
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {groups.length === 0 ? (
            <EmptyState text="No groups yet" description="Create a shared wallet for your next trip or house expense." linkTo="/groups" linkLabel="Create one" />
          ) : (
            <ul className="space-y-2">
              {groups.slice(0, 5).map((g, i) => (
                <li key={g.id} className="animate-fade-in" style={{ animationDelay: `${i * 40}ms` }}>
                  <Link
                    to={`/groups/${g.id}`}
                    className="group flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-3 transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:bg-brand-50/60"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-100 to-blue-100 text-brand-700">
                        <Users className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="font-semibold text-slate-800 transition-colors group-hover:text-brand-700">{g.name}</p>
                        <p className="text-[11px] text-slate-400">Shared wallet</p>
                      </div>
                    </div>
                    <span className={(groupBalances[g.id] || 0) >= 0 ? "text-sm font-bold text-emerald-600" : "text-sm font-bold text-rose-600"}>
                      {formatMoney(groupBalances[g.id] || 0)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="animate-fade-in rounded-2xl border border-blue-100 bg-white p-4 shadow-soft transition-all duration-300 hover:-translate-y-0.5 hover:shadow-soft-lg">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
                <CircleDollarSign className="h-4 w-4" />
              </div>
              <h2 className="text-base font-bold text-slate-800">Recent transactions</h2>
            </div>
            <Link to="/transactions" className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 transition-colors hover:text-brand-800">
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {transactions.length === 0 ? (
            <EmptyState text="No transactions yet" description="Your payment activity will show up here once someone settles a bill." />
          ) : (
            <ul className="space-y-2">
              {transactions.map((t, i) => (
                <li key={t.id} className="animate-fade-in" style={{ animationDelay: `${i * 40}ms` }}>
                  <Link
                    to={`/transactions/${t.id}`}
                    className="group flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-3 transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:bg-brand-50/60"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-800 transition-colors group-hover:text-brand-700">
                        {t.from_user_name} → {t.to_user_name}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-400">{formatDate(t.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-800">{formatMoney(t.amount)}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${StatusBadgeClasses(t.status)}`}>
                        {t.status}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, tone, delay, icon }) {
  const toneClasses = {
    emerald: {
      value: "text-emerald-600",
      badge: "bg-emerald-50 text-emerald-600",
      bar: "from-emerald-500 to-emerald-400",
    },
    rose: {
      value: "text-rose-600",
      badge: "bg-rose-50 text-rose-600",
      bar: "from-rose-500 to-rose-400",
    },
    brand: {
      value: "text-brand-700",
      badge: "bg-brand-50 text-brand-700",
      bar: "from-brand-500 to-brand-400",
    },
  };

  return (
    <div
      className="animate-scale-in group relative overflow-hidden rounded-2xl border border-blue-100 bg-white p-4 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-soft-lg"
      style={{ animationDelay: delay }}
    >
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${toneClasses[tone].bar}`} />
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">{label}</p>
          <p className={`mt-3 text-2xl font-black tracking-tight ${toneClasses[tone].value}`}>
            {value}
          </p>
        </div>
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${toneClasses[tone].badge}`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ text, description, linkTo, linkLabel }) {
  return (
    <div className="rounded-2xl border border-dashed border-brand-200 bg-gradient-to-br from-brand-50 via-white to-blue-50 p-6 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700">
        <CreditCard className="h-5 w-5" />
      </div>
      <p className="mt-4 text-base font-bold text-slate-800">{text}</p>
      {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      {linkTo && (
        <Link
          to={linkTo}
          className="mt-4 inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow"
        >
          {linkLabel}
        </Link>
      )}
    </div>
  );
}
