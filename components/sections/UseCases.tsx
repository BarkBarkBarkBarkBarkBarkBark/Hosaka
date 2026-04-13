import {
  Wifi,
  Wrench,
  Terminal,
  FlaskConical,
  AlertCircle,
  Layers,
} from "lucide-react"

const useCases = [
  {
    icon: Wifi,
    title: "Network Security",
    description:
      "Wireless audits, packet capture, network reconnaissance, and on-site assessment workflows — all in a backpack.",
  },
  {
    icon: Wrench,
    title: "Field Engineering",
    description:
      "Serial console access, GPIO tooling, cable testing, and infrastructure diagnostics directly on-site.",
  },
  {
    icon: Terminal,
    title: "Remote Development",
    description:
      "Full Linux environment with your IDE, toolchain, and SSH config. Consistent setup anywhere you work.",
  },
  {
    icon: FlaskConical,
    title: "Lab Operations",
    description:
      "Mobile lab setup for hardware experimentation, firmware development, and embedded research.",
  },
  {
    icon: AlertCircle,
    title: "Incident Response",
    description:
      "Rapid deployment kit for on-site triage, digital forensics, log analysis, and containment operations.",
  },
  {
    icon: Layers,
    title: "Custom Workflows",
    description:
      "Specialized configurations for teams, researchers, and use cases that standard hardware doesn't fit.",
  },
]

export default function UseCases() {
  return (
    <section className="py-24 bg-slate-950 border-t border-slate-800/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="max-w-xl mb-14">
          <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-4">
            Use Cases
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-100 tracking-tight mb-4">
            Built for the work you actually do.
          </h2>
          <p className="text-slate-400 leading-relaxed">
            Our decks are designed around real professional workflows — not
            hypothetical feature lists.
          </p>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {useCases.map(({ icon: Icon, title, description }) => (
            <div
              key={title}
              className="group flex gap-4 p-6 rounded-xl border border-slate-800 bg-slate-900/20 hover:border-slate-700 hover:bg-slate-900/40 transition-all duration-200"
            >
              <div className="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-blue-500/10 group-hover:border group-hover:border-blue-500/20 transition-colors">
                <Icon className="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-colors" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-200 mb-1.5">
                  {title}
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
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
