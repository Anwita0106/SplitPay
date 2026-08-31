import { ArrowRight, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm animate-fade-in">
      <div className="mb-8 text-center">
        <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-brand-400 text-white shadow-soft-lg">
          <ShieldCheck className="h-7 w-7" />
        </div>
        <h1 className="text-3xl font-black tracking-tight text-slate-900">
          Split<span className="bg-gradient-to-r from-brand-600 to-brand-400 bg-clip-text text-transparent">Pay</span>
        </h1>
        <p className="mt-1 text-sm text-slate-500">Smart expense sharing &amp; UPI settlement</p>
      </div>
      <form
        onSubmit={handleSubmit}
        className="animate-scale-in space-y-4 rounded-2xl border border-blue-100 bg-white/90 p-6 shadow-soft-lg backdrop-blur-sm"
      >
        <h2 className="text-lg font-bold text-slate-900">Log in</h2>
        {error && (
          <p className="animate-fade-in rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
        )}
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
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-blue-200 bg-slate-50 py-2.5 pl-9 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow active:scale-[0.98] disabled:opacity-60"
        >
          {submitting ? "Logging in..." : "Log in"}
          <ArrowRight className="h-4 w-4" />
        </button>
        <p className="text-center text-sm text-slate-500">
          No account?{" "}
          <Link to="/register" className="font-medium text-brand-600 transition-colors hover:text-brand-800 hover:underline">
            Register
          </Link>
        </p>
      </form>
    </div>
  );
}
