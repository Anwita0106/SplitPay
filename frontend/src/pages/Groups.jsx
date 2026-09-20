import { useEffect, useState } from "react";
import { ArrowRight, Plus, Sparkles, UserPlus, Users, X } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorState } from "../components/PageState.jsx";
import { useToast } from "../context/ToastContext.jsx";
import api from "../services/api";
import { getErrorCode, getErrorExtra, getErrorMessage } from "../utils/errors";

export default function Groups() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [emailsText, setEmailsText] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [duplicates, setDuplicates] = useState(null); // existing groups with the same name, when the API asks "create anyway?"
  const navigate = useNavigate();
  const toast = useToast();

  function load() {
    setLoading(true); setLoadError("");
    api.get("/groups")
      .then((res) => setGroups(res.data))
      .catch((err) => setLoadError(getErrorMessage(err, "Could not load your groups.")))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function handleCreate(e, allowDuplicate = false) {
    e?.preventDefault(); setError(""); setSubmitting(true);
    try {
      const member_emails = emailsText.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await api.post("/groups", { name, member_emails, allow_duplicate: allowDuplicate });
      toast.success(`“${res.data.name}” created.`);
      navigate(`/groups/${res.data.id}`);
    } catch (err) {
      if (getErrorCode(err) === "DUPLICATE_GROUP_NAME") { setDuplicates(getErrorExtra(err)?.existing || []); setError(""); }
      else { setDuplicates(null); setError(getErrorMessage(err, "Could not create group.")); }
    }
    finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-6 pb-8">
      <section className="relative overflow-hidden rounded-[30px] bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-8">
        <div className="absolute right-0 top-0 h-40 w-40 rounded-full bg-blue-100/60 blur-3xl" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div><span className="eyebrow">Your circles</span><h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">Groups</h1><p className="mt-2 max-w-xl text-sm leading-6 text-slate-500">Trips, roommates, dinners, and everything in between. Keep shared spending clear without chasing spreadsheets.</p></div>
          <button onClick={() => setShowForm((v) => !v)} className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-black text-white shadow-lg shadow-slate-950/10 hover:-translate-y-0.5 hover:bg-slate-800"><Plus className="h-4 w-4" /> {showForm ? "Close" : "New group"}</button>
        </div>
      </section>

      {showForm && <form onSubmit={handleCreate} className="animate-scale-in rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-5 flex items-center justify-between"><div><p className="eyebrow">Create a shared space</p><h2 className="mt-1 text-lg font-black text-slate-950">New group</h2></div><button type="button" onClick={() => setShowForm(false)} className="rounded-xl p-2 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4" /></button></div>
        {error && <p className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>}
        <div className="grid gap-4 md:grid-cols-2"><Field label="Group name" placeholder="Goa Trip" value={name} onChange={(v) => { setName(v); setDuplicates(null); }} required /><Field label="Member emails" hint="comma separated" placeholder="rahul@example.com, priya@example.com" value={emailsText} onChange={setEmailsText} /></div>
        {duplicates && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-700 dark:text-amber-300"><p className="font-bold">You already have {duplicates.length === 1 ? "a group" : `${duplicates.length} groups`} called “{name.trim()}”.</p><p className="mt-1">Open the existing one, rename this group, or create it anyway.</p><div className="mt-2 flex flex-wrap gap-2">{duplicates.map((d) => <Link key={d.id} to={`/groups/${d.id}`} className="rounded-lg border border-amber-200 bg-white px-2.5 py-1 font-bold text-slate-700 hover:bg-slate-50">Open “{d.name}”{d.member_count != null ? ` · ${d.member_count} members` : ""}</Link>)}<button type="button" disabled={submitting} onClick={() => handleCreate(null, true)} className="rounded-lg bg-slate-950 px-2.5 py-1 font-bold text-white hover:bg-slate-800 disabled:opacity-50">Create anyway</button></div></div>}
        <button disabled={submitting} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-black text-white shadow-lg shadow-blue-600/15 hover:bg-blue-700 disabled:opacity-50">{submitting ? "Creating..." : "Create group"}<ArrowRight className="h-4 w-4" /></button>
      </form>}

      {loadError ? <ErrorState message={loadError} onRetry={load} /> : loading ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[1,2,3].map((i)=><div key={i} className="skeleton h-44 rounded-3xl" />)}</div> : groups.length === 0 ? <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500"><Users /></div><h2 className="mt-4 text-lg font-black text-slate-800">Your first group is waiting.</h2><p className="mx-auto mt-1 max-w-sm text-sm text-slate-400">Create one for a trip, house, team, or dinner and invite everyone in seconds.</p><button onClick={() => setShowForm(true)} className="mt-5 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-black text-white">Create a group</button></div> : <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map((group, i) => <Link key={group.id} to={`/groups/${group.id}`} className="group relative overflow-hidden rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-1 hover:border-slate-300 hover:shadow-xl hover:shadow-slate-900/5" style={{animationDelay:`${i*45}ms`}}>
          <div className="absolute right-0 top-0 h-24 w-24 rounded-full bg-blue-50 blur-2xl transition group-hover:bg-cyan-50" />
          <div className="relative flex items-start justify-between"><div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-white"><Users className="h-5 w-5" /></div><span className="rounded-full bg-emerald-50 px-2 py-1 text-[9px] font-black uppercase tracking-wider text-emerald-700">Active</span></div>
          <div className="relative mt-5"><h3 className="truncate text-lg font-black text-slate-950 group-hover:text-blue-600">{group.name}</h3><p className="mt-1 text-[11px] text-slate-400">Created {new Date(group.created_at).toLocaleDateString()}{group.member_count ? ` · ${group.member_count} member${group.member_count === 1 ? "" : "s"}` : ""}</p></div>
          <div className="relative mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-[11px] font-bold text-slate-500"><span className="inline-flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-blue-500" /> Shared wallet</span><ArrowRight className="h-4 w-4 text-slate-300 transition group-hover:translate-x-1 group-hover:text-blue-600" /></div>
        </Link>)}
      </div>}
    </div>
  );
}

function Field({ label, hint, value, onChange, placeholder, required }) { return <div><label className="mb-1.5 block text-xs font-bold text-slate-700">{label} {hint && <span className="font-normal text-slate-400">({hint})</span>}</label><input required={required} value={value} onChange={(e)=>onChange(e.target.value)} placeholder={placeholder} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm text-slate-900 placeholder:text-slate-300 focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-100" /></div>; }
