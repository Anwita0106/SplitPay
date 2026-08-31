import { ArrowUpRight, CreditCard, LogOut, Sparkles, UserRound, Users, WalletCards } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const links = [
  { to: "/", label: "Dashboard", icon: WalletCards },
  { to: "/groups", label: "Groups", icon: Users },
  { to: "/transactions", label: "Transactions", icon: CreditCard },
  { to: "/profile", label: "Profile", icon: UserRound },
];

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  return (
    <header className="sticky top-0 z-20 border-b border-blue-100/80 bg-white/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-8">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50/80 px-2.5 py-1.5 transition-all duration-200 hover:scale-[1.02]">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-brand-600 to-blue-400 text-white shadow-soft">
              <Sparkles className="h-3.5 w-3.5" />
            </span>
            <span className="bg-gradient-to-r from-brand-700 to-brand-500 bg-clip-text text-base font-black tracking-tight text-transparent">
              Split<span className="text-slate-900">Pay</span>
            </span>
          </span>
          <nav className="hidden gap-1.5 sm:flex">
            {links.map((l) => {
              const Icon = l.icon;
              return (
                <NavLink
                  key={l.to}
                  to={l.to}
                  end={l.to === "/"}
                  className={({ isActive }) =>
                    `inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition-all duration-200 ${
                      isActive
                        ? "bg-brand-50 text-brand-700 shadow-sm ring-1 ring-brand-100"
                        : "text-slate-600 hover:bg-brand-50/60 hover:text-brand-700"
                    }`
                  }
                >
                  <Icon className="h-4 w-4" />
                  {l.label}
                </NavLink>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-600 sm:flex">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[10px] font-bold text-white">
              {user.name.charAt(0).toUpperCase()}
            </span>
            {user.name}
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all duration-200 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700 active:scale-[0.98]"
          >
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Log out</span>
          </button>
        </div>
      </div>
      <nav className="flex gap-1.5 border-t border-blue-50/80 px-4 py-2 sm:hidden">
        {links.map((l) => {
          const Icon = l.icon;
          return (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                `inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-2.5 py-2 text-xs font-semibold transition-all duration-200 ${
                  isActive ? "bg-brand-50 text-brand-700" : "text-slate-600"
                }`
              }
            >
              <Icon className="h-3.5 w-3.5" />
              {l.label}
            </NavLink>
          );
        })}
      </nav>
    </header>
  );
}
