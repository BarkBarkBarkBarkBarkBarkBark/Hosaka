"use client"

import { useActionState } from "react"
import { submitContactForm, initialState } from "@/lib/actions"
import { CheckCircle } from "lucide-react"

const inquiryTypes = [
  { value: "general", label: "General Inquiry" },
  { value: "product", label: "Product Question" },
  { value: "custom", label: "Custom Build Inquiry" },
  { value: "bulk", label: "Bulk / Organizational Order" },
  { value: "press", label: "Media / Press" },
  { value: "support", label: "Support" },
]

const inputClass =
  "w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"

export default function ContactForm() {
  const [state, action, pending] = useActionState(submitContactForm, initialState)

  if (state.success) {
    return (
      <div className="flex items-start gap-4 p-6 rounded-2xl border border-emerald-500/20 bg-emerald-500/5">
        <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-emerald-300 mb-1">
            Message received
          </p>
          <p className="text-sm text-emerald-400/70">{state.message}</p>
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
          htmlFor="type"
          className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
        >
          Inquiry Type
        </label>
        <select
          id="type"
          name="type"
          className={`${inputClass} cursor-pointer`}
          defaultValue="general"
        >
          {inquiryTypes.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor="message"
          className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2"
        >
          Message *
        </label>
        <textarea
          id="message"
          name="message"
          required
          rows={5}
          placeholder="What would you like to discuss?"
          className={`${inputClass} resize-none`}
        />
      </div>

      {state.message && (
        <p className="text-sm text-red-400">{state.message}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-full inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 disabled:opacity-60 text-white font-medium rounded-xl px-6 py-3.5 text-sm transition-colors cursor-pointer"
      >
        {pending ? "Sending..." : "Send Message"}
      </button>
    </form>
  )
}
