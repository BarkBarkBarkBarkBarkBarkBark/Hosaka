const differentiators = [
  {
    number: "01",
    title: "Preconfigured, not a parts list",
    description:
      "We don't ship you components and wish you luck. Every deck is assembled, imaged, and tested before it leaves our workshop. Your first boot should be productive — not a two-hour setup session.",
  },
  {
    number: "02",
    title: "Designed for real deployments",
    description:
      "From network assessments to field diagnostics, our hardware is built around workflows that happen outside the office. Form follows function. We test in conditions that actually occur.",
  },
  {
    number: "03",
    title: "No proprietary lock-in",
    description:
      "Everything we use is documented, accessible, and replaceable. We publish hardware specifications and support third-party software configurations. Your tools should work for you.",
  },
  {
    number: "04",
    title: "Upgrade paths built in",
    description:
      "As your needs grow, your deck can grow with you. We design for modularity and longevity — not planned obsolescence. Storage, RAM, and peripherals are user-serviceable by design.",
  },
]

export default function WhyUs() {
  return (
    <section className="py-24 bg-slate-950 border-t border-slate-800/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="max-w-xl mb-16">
          <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-4">
            Why CyberDeck
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-100 tracking-tight">
            Built differently, for a reason.
          </h2>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
          {differentiators.map(({ number, title, description }) => (
            <div
              key={number}
              className="group flex gap-6 p-8 rounded-2xl border border-slate-800 bg-slate-900/30 hover:border-slate-700 transition-colors"
            >
              {/* Number */}
              <span className="font-mono text-sm text-slate-700 tabular-nums shrink-0 pt-0.5 group-hover:text-blue-500/50 transition-colors">
                {number}
              </span>
              <div>
                <h3 className="text-base font-semibold text-slate-100 mb-3">
                  {title}
                </h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  {description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
