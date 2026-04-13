import type { Metadata } from "next"
import Button from "@/components/ui/Button"

export const metadata: Metadata = {
  title: "About",
  description:
    "CyberDeck builds portable computing systems for technical professionals — developers, security researchers, and field operators.",
}

const timeline = [
  {
    year: "The Problem",
    description:
      "Technical professionals were carrying too much, configuring too often, and working with hardware not designed for their actual environment. Laptops are powerful but fragile. Raspberry Pi kits are cheap but DIY. Nothing in between existed at a professional level.",
  },
  {
    year: "The Approach",
    description:
      "We started building custom portable systems for specific jobs: wireless assessments, field diagnostics, mobile development. Not experimental — functional. Not gamer hardware dressed up — real tools for real work.",
  },
  {
    year: "The Standard",
    description:
      "Every unit we ship is tested. Every configuration is documented. Every design decision is made with deployment in mind. We're building the category of professional portable computing from the ground up.",
  },
]

const values = [
  {
    title: "Functional over flashy",
    description:
      "We're not building status symbols. We're building tools. If it doesn't improve the work, it doesn't ship.",
  },
  {
    title: "Honest about limitations",
    description:
      "We publish specs accurately. We don't overclaim performance. You should know exactly what you're getting.",
  },
  {
    title: "Open by default",
    description:
      "No locked bootloaders. No hidden dependencies. No vendor agreements that restrict what you can run.",
  },
  {
    title: "Built for longevity",
    description:
      "We design for repairability and upgradability because that's what respect for the customer looks like.",
  },
]

export default function AboutPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      {/* Hero */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-20 border-b border-slate-800/60">
        <div className="max-w-3xl">
          <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-6">
            About CyberDeck
          </p>
          <h1 className="text-4xl sm:text-5xl font-bold text-slate-100 tracking-tight mb-6 leading-tight">
            We build portable systems for people who do technical work in the
            real world.
          </h1>
          <p className="text-xl text-slate-400 leading-relaxed">
            Not for the maker bench. Not for the gaming desk. For the field —
            wherever your field happens to be.
          </p>
        </div>
      </div>

      {/* Story */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 border-b border-slate-800/60">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
          <div>
            <h2 className="text-2xl font-bold text-slate-100 mb-6">
              Why we started
            </h2>
            <p className="text-slate-400 leading-relaxed mb-4">
              The cyberdeck concept has existed in the hardware community for
              years. Hundreds of hobbyists have built beautiful one-offs. But
              nothing purpose-built for working professionals existed at a
              consistent, reliable level.
            </p>
            <p className="text-slate-400 leading-relaxed mb-4">
              The gap wasn't technical. It was intent. Most kits are designed
              for experimentation, not deployment. For tinkering, not work.
            </p>
            <p className="text-slate-400 leading-relaxed">
              We set out to fill that gap — building professional-grade portable
              computing systems with the same attention to configuration,
              reliability, and documentation that enterprise hardware gets. Just
              smaller, lighter, and designed for the job.
            </p>
          </div>

          {/* Timeline */}
          <div className="space-y-8">
            {timeline.map(({ year, description }) => (
              <div key={year} className="flex gap-6">
                <div className="w-0.5 bg-slate-800 shrink-0 relative">
                  <div className="absolute top-1.5 -left-1 w-2.5 h-2.5 rounded-full bg-blue-500/40 border border-blue-500/60" />
                </div>
                <div className="pb-6">
                  <h3 className="text-sm font-mono font-semibold text-blue-400 uppercase tracking-widest mb-2">
                    {year}
                  </h3>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    {description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Values */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 border-b border-slate-800/60">
        <h2 className="text-2xl font-bold text-slate-100 mb-12">
          How we work
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {values.map(({ title, description }) => (
            <div
              key={title}
              className="p-8 rounded-2xl border border-slate-800 bg-slate-900/30"
            >
              <h3 className="text-base font-semibold text-slate-100 mb-3">
                {title}
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                {description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="max-w-xl">
          <h2 className="text-2xl font-bold text-slate-100 mb-4">
            See what we build
          </h2>
          <p className="text-slate-400 mb-8 leading-relaxed">
            Browse the current product lineup or reach out if you have a
            specialized requirement. We work with individuals, teams, and
            organizations.
          </p>
          <div className="flex flex-wrap gap-4">
            <Button href="/products" size="lg">
              View Products
            </Button>
            <Button href="/contact" size="lg" variant="secondary">
              Get in Touch
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
