import type { Metadata } from "next"
import { Clock, CheckCircle, Mail } from "lucide-react"
import PreorderForm from "./PreorderForm"

export const metadata: Metadata = {
  title: "Preorder",
  description:
    "Join the CyberDeck preorder list. Express interest in the Field Deck Lite, Operator Deck, or Custom Build Program and get early access pricing.",
}

const expectations = [
  {
    icon: Clock,
    title: "What happens next",
    description:
      "We'll review your submission and reach out with estimated availability and pricing details for your selected configuration.",
  },
  {
    icon: Mail,
    title: "No commitment required",
    description:
      "This form captures interest, not payment. You'll receive a formal preorder confirmation separately with deposit information.",
  },
  {
    icon: CheckCircle,
    title: "Priority fulfillment",
    description:
      "Preorder list members get first allocation and early-access pricing when production units are ready.",
  },
]

export default function PreorderPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-24">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
          {/* Left: info */}
          <div>
            <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-5">
              Preorder
            </p>
            <h1 className="text-4xl sm:text-5xl font-bold text-slate-100 tracking-tight mb-6">
              Reserve your spot.
            </h1>
            <p className="text-slate-400 leading-relaxed mb-12">
              Full checkout is not yet live. Express your interest here, and
              we&apos;ll contact you as availability opens for your selected
              configuration.
            </p>

            {/* What to expect */}
            <div className="space-y-5">
              {expectations.map(({ icon: Icon, title, description }) => (
                <div
                  key={title}
                  className="flex items-start gap-4 p-5 rounded-xl border border-slate-800 bg-slate-900/30"
                >
                  <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                    <Icon className="w-4 h-4 text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-200 mb-1">
                      {title}
                    </h3>
                    <p className="text-sm text-slate-500 leading-relaxed">
                      {description}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* Timeline note */}
            <div className="mt-8 p-5 rounded-xl border border-slate-800/60 bg-slate-900/20">
              <p className="text-xs font-mono uppercase tracking-widest text-slate-600 mb-2">
                Current Lead Time
              </p>
              <p className="text-2xl font-bold text-slate-100 font-mono">
                4–6 weeks
              </p>
              <p className="text-xs text-slate-600 mt-1">
                From order confirmation to delivery. Subject to change.
              </p>
            </div>
          </div>

          {/* Right: form */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8">
            <h2 className="text-lg font-semibold text-slate-100 mb-2">
              Preorder Interest Form
            </h2>
            <p className="text-sm text-slate-500 mb-8">
              Fields marked * are required.
            </p>
            <PreorderForm />
          </div>
        </div>
      </div>
    </div>
  )
}
