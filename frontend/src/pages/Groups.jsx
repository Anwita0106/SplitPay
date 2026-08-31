import { useEffect, useState } from "react";
import { Plus, Users, UserPlus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";

export default function Groups() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [emailsText, setEmailsText] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/groups").then((res) => {
      setGroups(res.data);
      setLoading(false);
    });
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const member_emails = emailsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await api.post("/groups", { name, member_emails });
      navigate(`/groups/${res.data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not create group.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="animate-fade-in flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="section-label">Your circles</p>
          <h1 className="fintech-header">Groups</h1>
          <p className="text-sm text-slate-500">Shared expenses with your people.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow active:scale-[0.98]"
        >
          <Plus className="h-4 w-4" />
          {showForm ? "Cancel" : "New group"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="animate-scale-in space-y-4 rounded-2xl border border-blue-100 bg-white p-5 shadow-soft"
        >
          {error && (
            <p className="animate-fade-in rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Group name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Goa Trip"
              className="w-full rounded-xl border border-blue-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Member emails <span className="font-normal text-slate-400">(comma separated)</span>
            </label>
            <input
              value={emailsText}
              onChange={(e) => setEmailsText(e.target.value)}
              placeholder="rahul@example.com, priya@example.com"
              className="w-full rounded-xl border border-blue-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow disabled:opacity-60"
          >
            {submitting ? "Creating..." : "Create group"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="skeleton h-32 rounded-2xl" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="animate-fade-in rounded-2xl border border-dashed border-brand-200 bg-gradient-to-br from-brand-50 via-white to-blue-50 p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-brand-700">
            <Users className="h-5 w-5" />
          </div>
          <p className="mt-4 text-lg font-bold text-slate-800">No groups yet</p>
          <p className="mt-1 text-sm text-slate-500">Create a shared wallet to start managing expenses together.</p>
          <button
            onClick={() => setShowForm(true)}
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-4 py-2 text-sm font-semibold text-white shadow-soft transition-all duration-200 hover:shadow-glow"
          >
            <UserPlus className="h-4 w-4" />
            Create one
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {groups.map((g, i) => (
            <Link
              key={g.id}
              to={`/groups/${g.id}`}
              className="group animate-fade-in rounded-2xl border border-blue-100 bg-white p-4 shadow-soft transition-all duration-200 hover:-translate-y-1 hover:border-brand-200 hover:shadow-soft-lg"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className="flex items-center justify-between">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-100 to-blue-100 text-brand-700">
                  <Users className="h-5 w-5" />
                </div>
                <span className="rounded-full border border-blue-100 bg-blue-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-brand-700">
                  Active
                </span>
              </div>
              <h3 className="mt-4 text-lg font-bold text-slate-900 transition-colors group-hover:text-brand-700">
                {g.name}
              </h3>
              <p className="mt-1 text-xs text-slate-400">Created {new Date(g.created_at).toLocaleDateString()}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
