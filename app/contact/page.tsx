import type { Metadata } from "next"
import { Mail, MessageSquare } from "lucide-react"
import ContactForm from "./ContactForm"

export const metadata: Metadata = {
  title: "Contact",
  description:
    "Get in touch with CyberDeck. Product questions, custom build inquiries, bulk orders, and press.",
}

export default function ContactPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-24">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
          {/* Left: info */}
          <div>
            <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-5">
              Contact
            </p>
            <h1 className="text-4xl sm:text-5xl font-bold text-slate-100 tracking-tight mb-6">
              Let&apos;s talk.
            </h1>
            <p className="text-slate-400 leading-relaxed mb-12">
              Whether you have a product question, want to discuss a custom
              build, or need to talk to someone about an organizational
              requirement — we&apos;re here.
            </p>

            {/* Contact options */}
            <div className="space-y-5">
              <div className="flex items-start gap-4 p-5 rounded-xl border border-slate-800 bg-slate-900/30">
                <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                  <Mail className="w-4 h-4 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-200 mb-1">
                    Email
                  </h3>
                  <p className="text-sm text-slate-500">
                    hello@cyberdeck.io
                  </p>
                  <p className="text-xs text-slate-600 mt-1">
                    We respond within 1–2 business days
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-5 rounded-xl border border-slate-800 bg-slate-900/30">
                <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                  <MessageSquare className="w-4 h-4 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-200 mb-1">
                    Custom Builds & Teams
                  </h3>
                  <p className="text-sm text-slate-500">
                    For custom configurations or orders of 3+ units, use the
                    inquiry type &quot;Custom Build&quot; or &quot;Bulk
                    Order&quot; in the form.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Right: form */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8">
            <h2 className="text-lg font-semibold text-slate-100 mb-6">
              Send a message
            </h2>
            <ContactForm />
          </div>
        </div>
      </div>
    </div>
  )
}
