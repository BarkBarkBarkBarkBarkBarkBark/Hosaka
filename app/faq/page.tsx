import type { Metadata } from "next"
import Link from "next/link"
import Accordion from "@/components/ui/Accordion"
import type { AccordionItem } from "@/components/ui/Accordion"

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Frequently asked questions about CyberDeck products, ordering, shipping, and support.",
}

const faqSections: { title: string; items: AccordionItem[] }[] = [
  {
    title: "Products",
    items: [
      {
        question: "What exactly is a cyberdeck?",
        answer:
          "A cyberdeck is a custom-built portable computing system — typically combining a compute module (Raspberry Pi or x86 SBC), a small display, an input device, and a battery in a compact, deployable enclosure. Our cyberdecks are professionally assembled and preconfigured, not DIY kits.",
      },
      {
        question: "Do your decks ship fully assembled?",
        answer:
          "Yes. Every unit ships fully assembled, tested, and imaged with the appropriate OS configuration. You do not need to source components, solder, assemble, or configure the software environment. Unbox, power on, and work.",
      },
      {
        question: "What software comes preinstalled?",
        answer:
          "Standard configurations ship with either Debian Linux or Kali Linux depending on the intended use case. Software environments are configured before shipping. Custom OS imaging, software configuration, and hardening are available through the Custom Build Program.",
      },
      {
        question: "What's the difference between the Field Deck Lite and the Operator Deck?",
        answer:
          "The Field Deck Lite is built around a Raspberry Pi 5 — portable, affordable, and suited for light-to-moderate workflows. The Operator Deck uses an x86 SBC for full Linux compatibility and more demanding work, with a larger display, longer battery life, modular expansion, and a reinforced chassis. Both ship preconfigured.",
      },
      {
        question: "Can I upgrade components later?",
        answer:
          "The Operator Deck is designed with user-accessible NVMe storage and RAM. The Field Deck Lite supports storage and peripheral expansion. We publish service documentation with every unit. The Custom Build Program can be designed around any specific upgrade path you require.",
      },
    ],
  },
  {
    title: "Ordering & Availability",
    items: [
      {
        question: "Are the products available to order now?",
        answer:
          "The Field Deck Lite and Operator Deck are currently in preorder. The Custom Build Program is open for consultation. Submit your interest via the Preorder page and we'll contact you as availability opens.",
      },
      {
        question: "What is the current lead time?",
        answer:
          "Current lead time is 4–6 weeks from order confirmation. Preorder list members receive priority fulfillment. Lead times are subject to component availability and will be communicated clearly at order confirmation.",
      },
      {
        question: "Do you offer team or bulk pricing?",
        answer:
          "Yes. For orders of 3 or more units, contact us through the Custom Build inquiry type or directly at hello@cyberdeck.io. We offer volume pricing and coordinated deployment support for organizational buyers.",
      },
      {
        question: "What payment methods do you accept?",
        answer:
          "Payment processing is not yet live for standard orders. Preorder deposits and custom build contracts are handled directly. Full checkout integration is in progress and will support major credit cards and wire transfer for organizational orders.",
      },
    ],
  },
  {
    title: "Usage & Legality",
    items: [
      {
        question: "Is it legal to use a cyberdeck?",
        answer:
          "Yes. Our decks are standard computing hardware sold for legitimate professional use: development, research, diagnostics, field engineering, and related technical workflows. They are subject to the same laws as any computer. Use them responsibly and in accordance with applicable local laws.",
      },
      {
        question: "Can I run my own OS or custom software?",
        answer:
          "Absolutely. No locked bootloaders. Full hardware access. You can reflash, reconfigure, or completely replace the OS. We document the hardware fully and support community configurations. The Custom Build Program also provides custom OS imaging as a service.",
      },
      {
        question: "Are these appropriate for security research?",
        answer:
          "Yes, with the standard caveat that security research must be conducted on systems and networks you own or have explicit written permission to test. Our hardware supports research workflows; using it on systems without authorization is illegal regardless of the tool.",
      },
    ],
  },
  {
    title: "Warranty & Support",
    items: [
      {
        question: "What warranty do you offer?",
        answer:
          "All units include a 90-day hardware warranty covering manufacturing defects and component failures under normal use. Extended warranty and support contracts are available for organizational purchasers. Contact us for details.",
      },
      {
        question: "What is your return policy?",
        answer:
          "Due to the custom-assembled nature of our products, all sales are final once production has begun. We stand firmly behind our build quality. If a unit arrives with a defect or damage in transit, contact us immediately and we will make it right.",
      },
      {
        question: "Do you offer ongoing support?",
        answer:
          "Yes. Email support is available for all customers. Extended support contracts, including SLA-based response times, are available for organizational purchasers through the Custom Build Program.",
      },
    ],
  },
]

export default function FAQPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-24">
        {/* Header */}
        <div className="mb-16">
          <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-4">
            FAQ
          </p>
          <h1 className="text-4xl sm:text-5xl font-bold text-slate-100 tracking-tight mb-4">
            Frequently asked questions
          </h1>
          <p className="text-slate-400 leading-relaxed">
            Can&apos;t find what you&apos;re looking for?{" "}
            <Link
              href="/contact"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              Send us a message
            </Link>
            .
          </p>
        </div>

        {/* Sections */}
        <div className="space-y-16">
          {faqSections.map(({ title, items }) => (
            <div key={title}>
              <h2 className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-5 border-b border-slate-800 pb-4">
                {title}
              </h2>
              <Accordion items={items} />
            </div>
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="mt-20 p-8 rounded-2xl border border-slate-800 bg-slate-900/30 text-center">
          <h3 className="text-lg font-semibold text-slate-100 mb-3">
            Still have questions?
          </h3>
          <p className="text-slate-400 text-sm mb-6">
            We respond to all inquiries within 1–2 business days.
          </p>
          <Link
            href="/contact"
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg px-6 py-3 text-sm transition-colors"
          >
            Contact Us
          </Link>
        </div>
      </div>
    </div>
  )
}
