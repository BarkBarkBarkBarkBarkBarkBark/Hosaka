import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "CyberDeck Privacy Policy.",
}

const lastUpdated = "April 2026"

export default function PrivacyPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-24">
        <p className="text-xs font-mono uppercase tracking-widest text-slate-600 mb-4">
          Last updated: {lastUpdated}
        </p>
        <h1 className="text-4xl font-bold text-slate-100 tracking-tight mb-4">
          Privacy Policy
        </h1>
        <p className="text-slate-400 leading-relaxed mb-12">
          We respect your privacy and are committed to being clear about what
          data we collect and why.
        </p>

        <div className="space-y-10 text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              1. Information We Collect
            </h2>
            <p className="leading-relaxed mb-3">
              We collect information you provide directly to us, including:
            </p>
            <ul className="space-y-2 list-none">
              {[
                "Name and email address when you submit interest or contact forms",
                "Company or organization name when provided",
                "Product preferences and use case information from preorder submissions",
                "Communications you send us",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500/50 shrink-0 mt-1.5" />
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              2. How We Use Your Information
            </h2>
            <p className="leading-relaxed mb-3">
              We use the information we collect to:
            </p>
            <ul className="space-y-2 list-none">
              {[
                "Process and fulfill orders and preorder inquiries",
                "Respond to your questions and communications",
                "Send transactional communications related to your order or inquiry",
                "Send product updates and launch notifications if you have opted in",
                "Improve our products and services",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500/50 shrink-0 mt-1.5" />
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              3. Data Sharing
            </h2>
            <p className="leading-relaxed">
              We do not sell, trade, or rent your personal information to third
              parties. We may share information with service providers who
              assist in operating our website and business (such as email
              delivery and payment processing) under confidentiality agreements.
              We may disclose information when required by law.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              4. Data Retention
            </h2>
            <p className="leading-relaxed">
              We retain your information for as long as necessary to fulfill
              the purposes described in this policy, including maintaining
              transaction records and providing ongoing support. You may
              request deletion of your data at any time.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              5. Cookies and Analytics
            </h2>
            <p className="leading-relaxed">
              Our website may use cookies for basic functionality and
              analytics. We do not use cross-site tracking cookies or
              advertising networks. Any analytics we use are configured to
              respect user privacy and minimize data collection.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              6. Your Rights
            </h2>
            <p className="leading-relaxed mb-3">
              Depending on your jurisdiction, you may have rights including:
            </p>
            <ul className="space-y-2 list-none">
              {[
                "Access to the personal data we hold about you",
                "Correction of inaccurate data",
                "Deletion of your personal data",
                "Opt-out of marketing communications",
                "Data portability",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500/50 shrink-0 mt-1.5" />
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              7. Security
            </h2>
            <p className="leading-relaxed">
              We implement reasonable technical and organizational measures to
              protect your information. No system is completely secure, and we
              cannot guarantee absolute security. Please contact us immediately
              if you suspect unauthorized access to your account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              8. Contact
            </h2>
            <p className="leading-relaxed">
              For privacy questions, data requests, or to exercise your rights,
              contact us at{" "}
              <a
                href="mailto:privacy@cyberdeck.io"
                className="text-blue-400 hover:text-blue-300 transition-colors"
              >
                privacy@cyberdeck.io
              </a>
              .
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
