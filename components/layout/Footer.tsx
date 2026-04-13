import Link from "next/link"
import { Terminal, ExternalLink } from "lucide-react"

const productLinks = [
  { href: "/products/field-deck-lite", label: "Field Deck Lite" },
  { href: "/products/operator-deck", label: "Operator Deck" },
  { href: "/products/custom-build", label: "Custom Build Program" },
  { href: "/preorder", label: "Preorder" },
]

const companyLinks = [
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
  { href: "/faq", label: "FAQ" },
]

const legalLinks = [
  { href: "/terms", label: "Terms of Service" },
  { href: "/privacy", label: "Privacy Policy" },
]

const socialLinks = [
  { href: "#", label: "GitHub" },
  { href: "#", label: "Twitter / X" },
  { href: "#", label: "LinkedIn" },
]

export default function Footer() {
  return (
    <footer className="bg-slate-950 border-t border-slate-800/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {/* Brand */}
          <div className="lg:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4 group">
              <Terminal className="w-4 h-4 text-blue-500" />
              <span className="font-mono font-bold text-slate-100 tracking-tight group-hover:text-blue-400 transition-colors text-sm">
                CYBER<span className="text-blue-500">/</span>DECK
              </span>
            </Link>
            <p className="text-slate-500 text-sm leading-relaxed mb-6">
              Portable computing systems built for technical professionals. 
              Preconfigured, field-ready, and open by design.
            </p>
            <div className="flex items-center gap-3">
              {socialLinks.map(({ href, label }) => (
                <a
                  key={label}
                  href={href}
                  aria-label={label}
                  className="w-8 h-8 rounded-lg border border-slate-800 flex items-center justify-center text-slate-500 hover:text-slate-300 hover:border-slate-700 transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              ))}
            </div>
          </div>

          {/* Products */}
          <div>
            <h3 className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-5">
              Products
            </h3>
            <ul className="space-y-3">
              {productLinks.map(({ href, label }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Company */}
          <div>
            <h3 className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-5">
              Company
            </h3>
            <ul className="space-y-3">
              {companyLinks.map(({ href, label }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-5">
              Legal
            </h3>
            <ul className="space-y-3">
              {legalLinks.map(({ href, label }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-16 pt-8 border-t border-slate-800/60 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-slate-600 font-mono">
            © {new Date().getFullYear()} CyberDeck. All rights reserved.
          </p>
          <p className="text-xs text-slate-700 font-mono">
            Built for professionals who work in the field.
          </p>
        </div>
      </div>
    </footer>
  )
}
