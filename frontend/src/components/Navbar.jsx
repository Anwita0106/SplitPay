import { Bot, CreditCard, LayoutDashboard, LogOut, Moon, Plus, ShieldCheck, Sun, UserRound, Users, WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const links = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/groups", label: "Groups", icon: Users },
  { to: "/ai", label: "AI", icon: Bot },
  { to: "/transactions", label: "Transactions", icon: CreditCard },
  { to: "/profile", label: "Profile", icon: UserRound },
];

export function ThemeToggle({ compact = false }) {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const saved = localStorage.getItem("splitpay_theme");
    return saved ? saved === "dark" : window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("splitpay_theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <button
      type="button"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      onClick={() => setDark((v) => !v)}
      className={`group inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 text-slate-700 shadow-sm backdrop-blur-xl hover:-translate-y-0.5 hover:border-slate-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 ${compact ? "h-10 w-10 justify-center" : "px-2.5 py-2"}`}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-950 text-white transition group-hover:rotate-12 dark:bg-white dark:text-slate-950">
        {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
      </span>
      {!compact && <span className="hidden text-[10px] font-black uppercase tracking-[.14em] sm:inline">{dark ? "Light" : "Dark"}</span>}
    </button>
  );
}

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!user) return null;

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-[#f7f0e3]/80 backdrop-blur-2xl dark:border-white/10 dark:bg-[#071523]/80">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 lg:px-6">
        <NavLink to="/" className="group flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center overflow-hidden rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-950/15">
            <WalletCards className="relative z-10 h-5 w-5" />
            <span className="absolute -right-2 -top-2 h-7 w-7 rounded-full bg-blue-500/70 blur-md" />
          </div>
          <div className="hidden sm:block">
            <p className="font-serif text-[18px] font-bold tracking-[-.03em] text-slate-950 dark:text-slate-100">SplitPay</p>
            <p className="text-[9px] font-black uppercase tracking-[0.18em] text-slate-400">Shared money, simplified</p>
          </div>
        </NavLink>

        <nav className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-1 rounded-2xl border border-slate-200 bg-slate-50/80 p-1 md:flex">
          {links.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-bold transition-all ${
                    isActive
                      ? "bg-white text-slate-950 shadow-sm ring-1 ring-slate-200"
                      : "text-slate-500 hover:bg-white/70 hover:text-slate-800"
                  }`
                }
              >
                <Icon className="h-3.5 w-3.5" />
                {link.label}
              </NavLink>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            onClick={() => navigate("/groups")}
            className="hidden items-center gap-2 rounded-xl bg-slate-950 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-slate-950/10 transition hover:-translate-y-0.5 hover:bg-slate-800 sm:inline-flex"
          >
            <Plus className="h-4 w-4" />
            New expense
          </button>
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-2 py-1.5 shadow-sm">
            <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-[11px] font-black text-white">
              {user.name?.charAt(0)?.toUpperCase() || "U"}
            </span>
            <span className="hidden max-w-24 truncate text-xs font-bold text-slate-700 lg:block">{user.name}</span>
            <button
              aria-label="Log out"
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="ml-0.5 rounded-lg p-1.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      <nav className="mx-auto flex max-w-7xl gap-1 px-4 pb-2 md:hidden">
        {links.map((link) => {
          const Icon = link.icon;
          return (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `flex flex-1 items-center justify-center gap-1.5 rounded-xl py-2 text-[11px] font-bold ${
                  isActive ? "bg-slate-100 text-slate-950" : "text-slate-400"
                }`
              }
            >
              <Icon className="h-3.5 w-3.5" />
              {link.label}
            </NavLink>
          );
        })}
      </nav>
      {location.pathname.startsWith("/groups/") && (
        <div className="hidden border-t border-slate-100 bg-slate-50/60 px-6 py-1.5 text-center text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400 lg:block">
          <ShieldCheck className="mr-1 inline h-3 w-3 text-emerald-500" /> Secure group workspace
        </div>
      )}
    </header>
  );
}
