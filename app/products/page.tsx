import type { Metadata } from "next"
import { products } from "@/data/products"
import ProductCard from "@/components/product/ProductCard"

export const metadata: Metadata = {
  title: "Products",
  description:
    "Browse the CyberDeck product lineup — from the entry-level Field Deck Lite to the full-capability Operator Deck and our Custom Build Program.",
}

export default function ProductsPage() {
  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      {/* Header */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-14 border-b border-slate-800/60">
        <p className="text-xs font-mono uppercase tracking-widest text-blue-400 mb-4">
          Product Lineup
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold text-slate-100 tracking-tight mb-4 max-w-xl">
          Three configurations. One standard.
        </h1>
        <p className="text-slate-400 max-w-2xl leading-relaxed">
          Every CyberDeck ships preconfigured and tested. Choose the
          configuration that matches your use case and budget — or work with us
          on something custom.
        </p>
      </div>

      {/* Product grid */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {products.map((product) => (
            <ProductCard key={product.slug} product={product} />
          ))}
        </div>

        {/* Bottom note */}
        <div className="mt-16 p-8 rounded-2xl border border-slate-800 bg-slate-900/30">
          <div className="flex flex-col sm:flex-row sm:items-center gap-6">
            <div className="flex-1">
              <h3 className="text-base font-semibold text-slate-100 mb-2">
                Need something more specialized?
              </h3>
              <p className="text-sm text-slate-400">
                The Custom Build Program covers configurations not listed here.
                Team deployments, specialized I/O, custom imaging, bulk orders.
              </p>
            </div>
            <a
              href="/products/custom-build"
              className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-slate-200 border border-slate-700 rounded-lg hover:bg-slate-800 hover:border-slate-600 transition-colors whitespace-nowrap"
            >
              Learn about Custom Builds →
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
