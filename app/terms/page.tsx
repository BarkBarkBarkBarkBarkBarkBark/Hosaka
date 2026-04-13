import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "CyberDeck Terms of Service.",
}

const lastUpdated = "April 2026"

export default function TermsPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-24">
        <p className="text-xs font-mono uppercase tracking-widest text-slate-600 mb-4">
          Last updated: {lastUpdated}
        </p>
        <h1 className="text-4xl font-bold text-slate-100 tracking-tight mb-4">
          Terms of Service
        </h1>
        <p className="text-slate-400 leading-relaxed mb-12">
          Please read these terms carefully before placing an order or using
          our website.
        </p>

        <div className="prose prose-invert prose-slate max-w-none space-y-10 text-slate-400">
          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              1. Acceptance of Terms
            </h2>
            <p className="leading-relaxed">
              By accessing or using the CyberDeck website or purchasing our
              products, you agree to be bound by these Terms of Service. If you
              do not agree to these terms, do not use our services.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              2. Products and Orders
            </h2>
            <p className="leading-relaxed mb-3">
              All orders are subject to availability and confirmation of the
              order price. We reserve the right to refuse or cancel any order
              at our discretion.
            </p>
            <p className="leading-relaxed">
              Product descriptions, specifications, and pricing are subject to
              change without notice. Images are illustrative and may not
              represent the final product exactly.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              3. Payment and Pricing
            </h2>
            <p className="leading-relaxed">
              All prices are in USD unless otherwise stated. Payment is due at
              the time of order confirmation or as specified in a custom build
              contract. We reserve the right to adjust pricing at any time
              prior to order confirmation.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              4. Shipping and Delivery
            </h2>
            <p className="leading-relaxed">
              Lead times are estimates only and are subject to change based on
              component availability and production capacity. We will
              communicate any significant delays promptly. Risk of loss
              transfers to the buyer upon delivery to the shipping carrier.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              5. Returns and Warranty
            </h2>
            <p className="leading-relaxed mb-3">
              Due to the custom-assembled nature of our products, all sales are
              final once production begins. Units arriving with manufacturing
              defects or transit damage will be repaired or replaced at our
              discretion.
            </p>
            <p className="leading-relaxed">
              All units include a 90-day hardware warranty covering
              manufacturing defects under normal use. The warranty does not
              cover damage from misuse, modification, or unauthorized repair.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              6. Acceptable Use
            </h2>
            <p className="leading-relaxed mb-3">
              Our products are sold for lawful purposes only. You agree to use
              our products in compliance with all applicable laws, regulations,
              and professional standards.
            </p>
            <p className="leading-relaxed">
              You expressly agree not to use our products to access systems,
              networks, or data without authorization; to conduct attacks or
              unauthorized intrusions; or for any illegal purpose. CyberDeck
              bears no responsibility for misuse of our hardware.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              7. Intellectual Property
            </h2>
            <p className="leading-relaxed">
              All content on this website, including text, images, and design,
              is the property of CyberDeck and protected by applicable
              intellectual property laws. You may not reproduce or distribute
              our content without written permission.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              8. Limitation of Liability
            </h2>
            <p className="leading-relaxed">
              To the fullest extent permitted by law, CyberDeck shall not be
              liable for any indirect, incidental, special, or consequential
              damages arising from your use of our products or services. Our
              total liability shall not exceed the amount paid for the
              applicable product or service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              9. Governing Law
            </h2>
            <p className="leading-relaxed">
              These terms shall be governed by and construed in accordance with
              the laws of the applicable jurisdiction, without regard to its
              conflict of law provisions.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-100 mb-4">
              10. Contact
            </h2>
            <p className="leading-relaxed">
              For questions about these Terms of Service, contact us at{" "}
              <a
                href="mailto:hello@cyberdeck.io"
                className="text-blue-400 hover:text-blue-300 transition-colors"
              >
                hello@cyberdeck.io
              </a>
              .
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
