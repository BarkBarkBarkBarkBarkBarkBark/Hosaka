"use client"

import { useActionState } from "react"
import { ArrowRight } from "lucide-react"
import { submitLeadForm, initialState } from "@/lib/actions"

export default function LeadCaptureCTA() {
  const [state, action, pending] = useActionState(submitLeadForm, initialState)

  return (
    <section className="py-24 bg-slate-950 border-t border-slate-800/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="relative rounded-2xl border border-slate-800 bg-slate-900/60 overflow-hidden px-8 py-16 sm:px-16 text-center">
          {/* Background glow */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_100%,rgba(59,130,246,0.08),transparent)]" />

          <div className="relative z-10 max-w-xl mx-auto">
            <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-4">
              Early Access
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-slate-100 tracking-tight mb-4">
              Be first in line.
            </h2>
            <p className="text-slate-400 leading-relaxed mb-8">
              Join the preorder list. Get early access pricing, product updates,
              and first allocation when we launch.
            </p>

            {state.success ? (
              <div className="inline-flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl px-6 py-4 text-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                {state.message}
              </div>
            ) : (
              <form action={action} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="email"
                  name="email"
                  placeholder="you@company.com"
                  required
                  className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-4 py-3 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                />
                <button
                  type="submit"
                  disabled={pending}
                  className="inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 disabled:opacity-60 text-white font-medium rounded-lg px-6 py-3 text-sm transition-colors whitespace-nowrap cursor-pointer"
                >
                  {pending ? "Joining..." : "Join Waitlist"}
                  {!pending && <ArrowRight className="w-4 h-4" />}
                </button>
              </form>
            )}

            {!state.success && state.message && (
              <p className="mt-3 text-sm text-red-400">{state.message}</p>
            )}

            <p className="mt-4 text-xs text-slate-600">
              No spam. Launch updates and early access only. Unsubscribe
              anytime.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
