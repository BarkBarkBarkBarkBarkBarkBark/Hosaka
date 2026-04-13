import type { Metadata } from "next"
import { notFound } from "next/navigation"
import Link from "next/link"
import { Terminal, ArrowLeft, Check } from "lucide-react"
import {
  getProductBySlug,
  getRelatedProducts,
  products,
} from "@/data/products"
import { formatPrice } from "@/lib/utils"
import Badge from "@/components/ui/Badge"
import Button from "@/components/ui/Button"
import ProductCard from "@/components/product/ProductCard"
import ProductSpecs from "@/components/product/ProductSpecs"
import Accordion from "@/components/ui/Accordion"

interface Props {
  params: Promise<{ slug: string }>
}

export async function generateStaticParams() {
  return products.map((p) => ({ slug: p.slug }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const product = getProductBySlug(slug)
  if (!product) return {}
  return {
    title: product.name,
    description: product.shortDescription,
  }
}

const productFaqs = [
  {
    question: "Does this ship fully assembled?",
    answer:
      "Yes. Every CyberDeck ships fully assembled, tested, and imaged. You do not need to source parts, assemble the hardware, or configure the OS from scratch. Open the box and boot up.",
  },
  {
    question: "What OS comes preinstalled?",
    answer:
      "Standard models ship with a configured Debian or Kali Linux environment depending on your selected use case profile. Custom OS configurations are available through the Custom Build Program.",
  },
  {
    question: "Can I upgrade components later?",
    answer:
      "The Operator Deck is designed with user-accessible storage and RAM. The Field Deck Lite supports storage and peripheral expansion. Detailed service documentation is included with every unit.",
  },
  {
    question: "What is the shipping lead time?",
    answer:
      "Current lead time is 4–6 weeks from order confirmation. Preorder customers receive priority fulfillment and will be notified as availability opens.",
  },
  {
    question: "Is there a warranty?",
    answer:
      "All units include a 90-day hardware warranty covering manufacturing defects and component failures. Extended warranty and support contracts are available for organizational purchasers.",
  },
]

export default async function ProductDetailPage({ params }: Props) {
  const { slug } = await params
  const product = getProductBySlug(slug)

  if (!product) notFound()

  const related = getRelatedProducts(slug)
  const isCustom = product.startingPrice === null

  return (
    <div className="bg-slate-950 min-h-screen pt-24">
      {/* Breadcrumb */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-10 pb-2">
        <Link
          href="/products"
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors font-mono"
        >
          <ArrowLeft className="w-3 h-3" />
          Products
        </Link>
      </div>

      {/* Product hero */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-start">
          {/* Gallery placeholder */}
          <div className="sticky top-24">
            <div className="aspect-square rounded-2xl border border-slate-800 bg-slate-900/60 flex flex-col items-center justify-center gap-3 text-slate-700">
              <Terminal className="w-12 h-12" />
              <span className="text-xs font-mono uppercase tracking-widest">
                Product renders coming soon
              </span>
            </div>
          </div>

          {/* Info panel */}
          <div>
            {/* Badges */}
            <div className="flex items-center gap-2 mb-5">
              {product.preorderOnly && (
                <Badge variant="accent">Preorder Only</Badge>
              )}
              {!product.preorderOnly && product.available && (
                <Badge variant="success">Available</Badge>
              )}
            </div>

            {/* Name */}
            <h1 className="text-4xl sm:text-5xl font-bold text-slate-100 tracking-tight mb-2">
              {product.name}
            </h1>
            <p className="text-blue-400 font-mono text-sm mb-5">
              {product.tagline}
            </p>

            {/* Price */}
            <p className="text-2xl font-bold text-slate-100 font-mono mb-6">
              {isCustom ? "Custom pricing" : `From ${formatPrice(product.startingPrice)}`}
            </p>

            {/* Description */}
            <p className="text-slate-400 leading-relaxed mb-8">
              {product.shortDescription}
            </p>

            {/* Key features */}
            <ul className="space-y-2 mb-8">
              {product.features.map((feature) => (
                <li
                  key={feature}
                  className="flex items-start gap-3 text-sm text-slate-300"
                >
                  <Check className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                  {feature}
                </li>
              ))}
            </ul>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row gap-3">
              {isCustom ? (
                <Button href="/contact" size="lg" className="flex-1">
                  Request a Consultation
                </Button>
              ) : (
                <Button href="/preorder" size="lg" className="flex-1">
                  Join Preorder List
                </Button>
              )}
              <Button
                href="/contact"
                size="lg"
                variant="secondary"
                className="flex-1"
              >
                Ask a Question
              </Button>
            </div>

            <p className="mt-4 text-xs text-slate-600 font-mono">
              90-day hardware warranty · Ships in 4–6 weeks · Open hardware
            </p>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-slate-800/60 mt-8" />

      {/* Specs + overview */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16">
          {/* Specs */}
          <div>
            <h2 className="text-xl font-bold text-slate-100 mb-6">
              Technical Specifications
            </h2>
            <ProductSpecs specs={product.specs} />
          </div>

          {/* Overview + use cases */}
          <div>
            <h2 className="text-xl font-bold text-slate-100 mb-4">Overview</h2>
            <div className="space-y-3 text-slate-400 leading-relaxed text-sm mb-10">
              {product.longDescription.split("\n\n").map((para, i) => (
                <p key={i}>{para.trim()}</p>
              ))}
            </div>

            <h3 className="text-base font-semibold text-slate-100 mb-4">
              Ideal Use Cases
            </h3>
            <ul className="space-y-2">
              {product.useCases.map((uc) => (
                <li
                  key={uc}
                  className="flex items-center gap-3 text-sm text-slate-400"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500/50 shrink-0" />
                  {uc}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* FAQ */}
      <div className="border-t border-slate-800/60">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <h2 className="text-2xl font-bold text-slate-100 mb-3">
            Frequently Asked Questions
          </h2>
          <p className="text-slate-500 text-sm mb-10">
            More questions?{" "}
            <Link
              href="/faq"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              See the full FAQ
            </Link>{" "}
            or{" "}
            <Link
              href="/contact"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              contact us
            </Link>
            .
          </p>
          <div className="max-w-3xl">
            <Accordion items={productFaqs} />
          </div>
        </div>
      </div>

      {/* Related products */}
      {related.length > 0 && (
        <div className="border-t border-slate-800/60">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
            <h2 className="text-2xl font-bold text-slate-100 mb-10">
              Related Products
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {related.map((p) => (
                <ProductCard key={p.slug} product={p} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
