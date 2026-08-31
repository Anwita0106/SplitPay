import { BadgeCheck, UserRound } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { formatDate } from "../utils/format";

export default function Profile() {
  const { user } = useAuth();

  return (
    <div className="mx-auto max-w-md">
      <div className="mb-5 animate-fade-in">
        <p className="section-label">Account</p>
        <h1 className="fintech-header">Profile</h1>
      </div>
      <div className="animate-scale-in overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-soft transition-shadow duration-300 hover:shadow-soft-lg">
        <div className="bg-gradient-to-r from-brand-600 via-brand-500 to-blue-400 p-6 text-white">
          <div className="mb-4 flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/15 text-xl font-black text-white ring-2 ring-white/30 backdrop-blur-sm">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div>
              <p className="text-lg font-bold">{user.name}</p>
              <p className="text-sm text-blue-100">{user.email}</p>
            </div>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-xs font-semibold text-blue-50">
            <BadgeCheck className="h-3.5 w-3.5" />
            Verified member
          </div>
        </div>
        <div className="p-6">
          <dl className="divide-y divide-blue-50">
            <div className="flex items-center justify-between py-3 text-sm">
              <dt className="flex items-center gap-2 text-slate-500">
                <UserRound className="h-4 w-4 text-brand-500" />
                Member since
              </dt>
              <dd className="font-semibold text-slate-800">{formatDate(user.created_at)}</dd>
            </div>
            <div className="flex items-center justify-between py-3 text-sm">
              <dt className="text-slate-500">User ID</dt>
              <dd className="font-mono text-xs text-slate-500">{user.id}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
