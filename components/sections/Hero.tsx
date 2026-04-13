"use client"

import { motion } from "framer-motion"
import { ArrowRight } from "lucide-react"
import Button from "@/components/ui/Button"

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.05 },
  },
}

const item = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: "easeOut" as const },
  },
}

const stats = [
  { value: "3", label: "Configurations" },
  { value: "6–12h", label: "Battery Life" },
  { value: "90-day", label: "Warranty" },
]

export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-slate-950">
      {/* Grid background */}
      <div className="absolute inset-0 bg-grid" />

      {/* Radial blue glow */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_40%_at_50%_0%,rgba(59,130,246,0.12),transparent)]" />

      {/* Bottom fade */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-slate-950 to-transparent" />

      <div className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-32 text-center">
        <motion.div variants={container} initial="hidden" animate="show">
          {/* Badge */}
          <motion.div variants={item} className="flex justify-center mb-8">
            <span className="inline-flex items-center gap-2 bg-slate-900/80 border border-slate-800 text-blue-400 text-xs font-mono uppercase tracking-widest rounded-full px-4 py-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
              Preorders opening soon
            </span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            variants={item}
            className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight text-slate-100 leading-[1.06] mb-6"
          >
            Portable systems
            <br />
            <span className="text-blue-400">built for technical</span>
            <br />
            work.
          </motion.h1>

          {/* Subheadline */}
          <motion.p
            variants={item}
            className="text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            Preconfigured cyberdecks for developers, security researchers, and
            field operators. Ready to deploy out of the box — no assembly
            required.
          </motion.p>

          {/* CTAs */}
          <motion.div
            variants={item}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Button href="/products" size="lg">
              Explore Products
              <ArrowRight className="w-4 h-4" />
            </Button>
            <Button href="/preorder" size="lg" variant="secondary">
              Join Preorder List
            </Button>
          </motion.div>

          {/* Stats strip */}
          <motion.div
            variants={item}
            className="mt-20 pt-10 border-t border-slate-800/60 grid grid-cols-3 gap-6 max-w-sm mx-auto"
          >
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-xl sm:text-2xl font-bold text-slate-100 font-mono tabular-nums">
                  {stat.value}
                </div>
                <div className="text-xs text-slate-600 mt-1 font-mono uppercase tracking-wider">
                  {stat.label}
                </div>
              </div>
            ))}
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}
