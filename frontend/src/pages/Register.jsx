import { ArrowRight, LockKeyhole, Mail, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { ThemeToggle } from "../components/Navbar.jsx";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register(name, email, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative mx-auto grid min-h-[calc(100vh-6rem)] w-full max-w-6xl items-center gap-10 py-8 lg:grid-cols-[1.15fr_.7fr]">
      <div className="hidden lg:block">
        <span className="editorial-kicker">SHARED MONEY · SIMPLIFIED</span>
        <h1 className="mt-7 max-w-2xl text-6xl leading-[.98] text-slate-950 dark:text-slate-100">
          Make every shared expense feel <em className="text-[#2e5f91] dark:text-[#86b8e8]">effortless.</em>
        </h1>
        <p className="mt-6 max-w-xl text-base leading-7 text-slate-600 dark:text-slate-300">
          Split trips, dinners and everyday costs with exact money calculations, transparent balances, and reliable settlement flows.
        </p>
        <div className="mt-10 grid max-w-xl grid-cols-3 gap-5 border-t border-slate-300/60 pt-6 dark:border-white/10">
          <div><p className="text-2xl font-black text-slate-950 dark:text-white">8</p><p className="mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">DB tables</p></div>
          <div><p className="text-2xl font-black text-slate-950 dark:text-white">35</p><p className="mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">Tests</p></div>
          <div><p className="text-2xl font-black text-slate-950 dark:text-white">O(n log n)</p><p className="mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">Settlement</p></div>
        </div>
      </div>
      <div className="relative mx-auto w-full max-w-sm animate-fade-in pt-8">
      <div className="absolute -right-2 -top-2"><ThemeToggle compact /></div>
      <div className="mb-8 text-center">
        <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-brand-400 text-white shadow-soft-lg">
          <UserRound className="h-7 w-7" />
        </div>
        <h1 className="text-3xl font-black tracking-tight text-slate-900">
          Split<span className="bg-gradient-to-r from-brand-600 to-brand-400 bg-clip-text text-transparent">Pay</span>
        </h1>
        <p className="mt-1 text-sm text-slate-500">Create your account</p>
      </div>
      <form
        onSubmit={handleSubmit}
        className="animate-scale-in space-y-4 rounded-[30px] border border-slate-200 bg-white/75 p-7 shadow-2xl shadow-slate-900/10 backdrop-blur-2xl dark:border-white/10 dark:bg-white/5 backdrop-blur-sm"
      >
        <h2 className="text-lg font-bold text-slate-900">Register</h2>
        {error && (
          <p className="animate-fade-in rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
        )}
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Full name</label>
          <div className="relative">
            <UserRound className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-xl border border-blue-200 bg-slate-50 py-2.5 pl-9 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Email</label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-blue-200 bg-slate-50 py-2.5 pl-9 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Password</label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-blue-200 bg-slate-50 py-2.5 pl-9 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <p className="mt-1 text-xs text-slate-400">At least 8 characters.</p>
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow active:scale-[0.98] disabled:opacity-60"
        >
          {submitting ? "Creating account..." : "Create account"}
          <ArrowRight className="h-4 w-4" />
        </button>
        <p className="text-center text-sm text-slate-500">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-brand-600 transition-colors hover:text-brand-800 hover:underline">
            Log in
          </Link>
        </p>
      </form>
      </div>
    </div>
  );
}
