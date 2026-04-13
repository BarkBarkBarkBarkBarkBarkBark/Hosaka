import { Zap, Shield, Code2 } from "lucide-react"

const values = [
  {
    icon: Zap,
    title: "Deploy Immediately",
    description:
      "Every deck ships fully assembled, tested, and configured. Boot up, connect, and get to work. No setup spiral, no spare parts box.",
  },
  {
    icon: Shield,
    title: "Field-Ready Hardware",
    description:
      "Built around real operational needs. Portable, durable, and designed for environments where reliability is not a nice-to-have.",
  },
  {
    icon: Code2,
    title: "Open by Design",
    description:
      "Full hardware access, no locked bootloaders, no vendor restrictions. Configure, extend, and upgrade to match your exact workflow.",
  },
]

export default function ValueProp() {
  return (
    <section className="py-24 bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {values.map(({ icon: Icon, title, description }) => (
            <div
              key={title}
              className="group p-8 rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/60 transition-all duration-300"
            >
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-6 group-hover:bg-blue-500/15 transition-colors">
                <Icon className="w-5 h-5 text-blue-400" />
              </div>
              <h3 className="text-base font-semibold text-slate-100 mb-3">
                {title}
              </h3>
              <p className="text-slate-400 leading-relaxed text-sm">
                {description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
