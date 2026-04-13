"use client"

import { useActionState } from "react"
import { submitPreorderForm, initialState } from "@/lib/actions"
import { CheckCircle } from "lucide-react"

const products = [
  { value: "field-deck-lite", label: "Field Deck Lite — From $349" },
  { value: "operator-deck", label: "Operator Deck — From $699" },
  { value: "custom-build", label: "Custom Build Program — Custom pricing" },
  { value: "undecided", label: "Not sure yet — need guidance" },
]

const budgetRanges = [
  { value: "under-500", label: "Under $500" },
  { value: "500-1000", label: "$500 – $1,000" },
  { value: "1000-2500", label: "$1,000 – $2,500" },
  { value: "2500-plus", label: "$2,500+" },
  { value: "team-budget", label: "Team / organizational budget" },
]

const inputClass =
  "w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"

export default function PreorderForm() {
  const [state, action, pending] = useActionState(
    submitPreorderForm,
    initialState
  )

  if (state.success) {
    return (
      <div className="flex items-start gap-4 p-8 rounded-2xl border border-emerald-500/20 bg-emerald-500/5">
        <CheckCircle className="w-6 h-6 text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-base font-semibold text-emerald-300 mb-2">
            You&apos;re on the list
          </p>
          <p className="text-sm text-emerald-400/70 leading-relaxed">
            {state.message}
          </p>
        </div>
      </div>
    )
  }

  return (
    <form action={action} className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div>
          <label
            htmlFor="name"
            className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
          >
            Name *
          </label>
          <input
            id="name"
            name="name"
            type="text"
            required
            placeholder="Your name"
            className={inputClass}
          />
        </div>
        <div>
          <label
            htmlFor="email"
            className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
          >
            Email *
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            placeholder="you@company.com"
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label
          htmlFor="company"
          className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
        >
          Company / Organization{" "}
          <span className="text-slate-700 normal-case not-italic">(optional)</span>
        </label>
        <input
          id="company"
          name="company"
          type="text"
          placeholder="Your company or organization"
          className={inputClass}
        />
      </div>

      <div>
        <label
          htmlFor="product"
          className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
        >
          Product Interest *
        </label>
        <select
          id="product"
          name="product"
          required
          className={`${inputClass} cursor-pointer`}
          defaultValue=""
        >
          <option value="" disabled>
            Select a configuration
          </option>
          {products.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor="useCase"
          className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
        >
          Primary Use Case{" "}
          <span className="text-slate-700 normal-case">(optional)</span>
        </label>
        <textarea
          id="useCase"
          name="useCase"
          rows={3}
          placeholder="Briefly describe what you'll use the deck for..."
          className={`${inputClass} resize-none`}
        />
      </div>

      <div>
        <label
          htmlFor="budget"
          className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
        >
          Budget Range{" "}
          <span className="text-slate-700 normal-case">(optional)</span>
        </label>
        <select
          id="budget"
          name="budget"
          className={`${inputClass} cursor-pointer`}
          defaultValue=""
        >
          <option value="">Prefer not to say</option>
          {budgetRanges.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {state.message && (
        <p className="text-sm text-red-400">{state.message}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-full inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 disabled:opacity-60 text-white font-medium rounded-xl px-6 py-3.5 text-sm transition-colors cursor-pointer"
      >
        {pending ? "Submitting..." : "Submit Preorder Interest"}
      </button>

      <p className="text-xs text-slate-600 text-center">
        This is not a binding purchase. We&apos;ll follow up with availability
        details and deposit information.
      </p>
    </form>
  )
}
