import Link from "next/link"
import { ArrowRight, Terminal } from "lucide-react"
import { type Product } from "@/data/products"
import { formatPrice } from "@/lib/utils"
import Badge from "@/components/ui/Badge"

interface ProductCardProps {
  product: Product
  featured?: boolean
}

export default function ProductCard({
  product,
  featured = false,
}: ProductCardProps) {
  const isCustom = product.startingPrice === null

  return (
    <div
      className={`group relative flex flex-col rounded-2xl border transition-all duration-300 overflow-hidden
        ${featured
          ? "border-blue-500/30 bg-slate-900/80 hover:border-blue-500/50"
          : "border-slate-800 bg-slate-900/40 hover:border-slate-700"
        }`}
    >
      {/* Subtle top accent line */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-blue-500/30 to-transparent" />

      {/* Image placeholder */}
      <div className="relative h-48 bg-slate-950/60 border-b border-slate-800/60 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2 text-slate-700">
          <Terminal className="w-8 h-8" />
          <span className="text-xs font-mono uppercase tracking-widest">
            Renders coming soon
          </span>
        </div>
        {product.preorderOnly && (
          <div className="absolute top-3 right-3">
            <Badge variant="accent">Preorder</Badge>
          </div>
        )}
        {!product.preorderOnly && product.available && (
          <div className="absolute top-3 right-3">
            <Badge variant="success">Available</Badge>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex flex-col flex-1 p-6">
        {/* Price */}
        <p className="text-xs font-mono text-slate-500 mb-2">
          {isCustom ? "Custom pricing" : `From ${formatPrice(product.startingPrice)}`}
        </p>

        {/* Name + tagline */}
        <h3 className="text-lg font-semibold text-slate-100 mb-1 group-hover:text-blue-300 transition-colors">
          {product.name}
        </h3>
        <p className="text-xs font-mono text-blue-400/70 mb-4">
          {product.tagline}
        </p>
        <p className="text-sm text-slate-400 leading-relaxed mb-6 flex-1">
          {product.shortDescription}
        </p>

        {/* Key specs */}
        <ul className="space-y-1.5 mb-6">
          {product.specs.slice(0, 4).map((spec) => (
            <li
              key={spec}
              className="flex items-center gap-2 text-xs text-slate-500"
            >
              <span className="w-1 h-1 rounded-full bg-blue-500/50 shrink-0" />
              {spec}
            </li>
          ))}
        </ul>

        {/* CTA */}
        <Link
          href={`/products/${product.slug}`}
          className="inline-flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-slate-700 text-sm font-medium text-slate-300 hover:bg-slate-800 hover:border-slate-600 hover:text-slate-100 transition-all duration-200"
        >
          View Details
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  )
}
