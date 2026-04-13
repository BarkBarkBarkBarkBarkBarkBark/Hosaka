"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Menu, X, Terminal } from "lucide-react"
import { cn } from "@/lib/utils"
import Button from "@/components/ui/Button"

const navLinks = [
  { href: "/products", label: "Products" },
  { href: "/about", label: "About" },
  { href: "/faq", label: "FAQ" },
  { href: "/contact", label: "Contact" },
]

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const pathname = usePathname()

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 16)
    window.addEventListener("scroll", handleScroll, { passive: true })
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  // Close mobile menu on route change
  useEffect(() => {
    setIsOpen(false)
  }, [pathname])

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
        scrolled
          ? "bg-slate-950/90 backdrop-blur-md border-b border-slate-800/60 shadow-xl shadow-slate-950/50"
          : "bg-transparent"
      )}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 group shrink-0">
            <Terminal className="w-4 h-4 text-blue-500" />
            <span className="font-mono font-bold text-slate-100 tracking-tight group-hover:text-blue-400 transition-colors text-sm">
              CYBER<span className="text-blue-500">/</span>DECK
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-7">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "text-sm font-medium transition-colors hover:text-slate-100",
                  pathname.startsWith(link.href)
                    ? "text-slate-100"
                    : "text-slate-400"
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          {/* Desktop CTA */}
          <div className="hidden md:flex items-center">
            <Button href="/preorder" size="sm">
              Preorder
            </Button>
          </div>

          {/* Mobile toggle */}
          <button
            className="md:hidden p-2 -mr-2 text-slate-400 hover:text-slate-100 transition-colors rounded-lg hover:bg-slate-800/50"
            onClick={() => setIsOpen(!isOpen)}
            aria-label="Toggle navigation menu"
          >
            {isOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      <div
        className={cn(
          "md:hidden border-t border-slate-800/60 bg-slate-950/95 backdrop-blur-md overflow-hidden transition-all duration-300",
          isOpen ? "max-h-[400px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="max-w-7xl mx-auto px-4 py-5 flex flex-col gap-1">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "text-sm font-medium py-2.5 px-3 rounded-lg transition-colors hover:bg-slate-800/60 hover:text-slate-100",
                pathname.startsWith(link.href)
                  ? "text-slate-100 bg-slate-800/40"
                  : "text-slate-400"
              )}
            >
              {link.label}
            </Link>
          ))}
          <div className="pt-3 border-t border-slate-800/60 mt-2">
            <Button href="/preorder" className="w-full justify-center">
              Preorder
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}
