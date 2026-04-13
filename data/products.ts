export interface Product {
  slug: string
  name: string
  tagline: string
  shortDescription: string
  longDescription: string
  startingPrice: number | null
  specs: string[]
  features: string[]
  useCases: string[]
  images: string[]
  featured: boolean
  available: boolean
  preorderOnly: boolean
}

export const products: Product[] = [
  {
    slug: "field-deck-lite",
    name: "Field Deck Lite",
    tagline: "Entry portable cyberdeck for fast deployment",
    shortDescription:
      "A low-cost, preconfigured cyberdeck built for mobile computing, experimentation, and field-ready workflows.",
    longDescription:
      "The Field Deck Lite is your entry point into purpose-built portable computing. Built around a Raspberry Pi 5 compute core, it ships fully assembled and imaged — no assembly, no setup spiral. Open the case, plug in, and you're operational.\n\nDesigned for developers who need a reliable portable environment, security researchers running lightweight assessments, and field operators who need a compact kit that just works. The Lite strips out everything you don't need and delivers exactly what you do.",
    startingPrice: 349,
    specs: [
      "Raspberry Pi 5 (8GB RAM)",
      "7\" IPS display — 1024×600",
      "Compact mechanical keyboard",
      "10,000mAh Li-ion battery",
      "6–8h estimated runtime",
      "Preconfigured Debian / Kali Linux",
      "USB-A ×3, USB-C, micro HDMI out",
      "Wi-Fi 6 + Bluetooth 5.2",
      "microSD + USB storage",
    ],
    features: [
      "Ships fully assembled and tested",
      "Preconfigured OS — boot and work",
      "Backpack-portable form factor",
      "Open hardware — no locked bootloaders",
      "Supports standard USB peripherals",
      "Field-serviceable battery",
    ],
    useCases: [
      "Portable development environment",
      "Network toolkit and diagnostics",
      "Security research and CTF competitions",
      "Field scripting and automation",
      "Education and hands-on training labs",
    ],
    images: [],
    featured: true,
    available: false,
    preorderOnly: true,
  },
  {
    slug: "operator-deck",
    name: "Operator Deck",
    tagline: "Ruggedized portable workstation",
    shortDescription:
      "A more capable cyberdeck designed for demanding users who want more power, durability, and upgrade paths.",
    longDescription:
      "The Operator Deck is built for professionals who need a portable workstation capable of sustained, demanding use. With x86 compute, a larger battery, and a modular expansion framework, it handles heavy tooling in the field, extended deployments, and requirements that evolve over time.\n\nRuggedized for transport and designed for real operational environments, the Operator Deck is the tool for users who treat their hardware as seriously as their work.",
    startingPrice: 699,
    specs: [
      "Intel N100 x86 SBC (16GB RAM)",
      "10.1\" IPS display — 1920×1200",
      "Full-travel compact keyboard",
      "20,000mAh high-density battery",
      "8–12h estimated runtime",
      "Preconfigured Debian / Kali Linux",
      "USB-A ×4, USB-C ×2, HDMI 2.0, RJ45",
      "Wi-Fi 6E + Bluetooth 5.3",
      "M.2 NVMe slot (user-accessible)",
      "GPIO / serial breakout header",
    ],
    features: [
      "x86 architecture — full Linux compatibility",
      "Modular accessory expansion rail",
      "User-accessible NVMe and RAM",
      "Reinforced chassis for field transport",
      "Larger display for extended sessions",
      "Dual USB-C with PD charging",
    ],
    useCases: [
      "Penetration testing and red team operations",
      "Field engineering and infrastructure work",
      "Remote development and deployment",
      "Network operations and monitoring",
      "Incident response and digital forensics",
      "Hardware research and lab operations",
    ],
    images: [],
    featured: true,
    available: false,
    preorderOnly: true,
  },
  {
    slug: "custom-build",
    name: "Custom Build Program",
    tagline: "Built around your mission",
    shortDescription:
      "Custom cyberdeck design and configuration for teams, researchers, and specialized deployments.",
    longDescription:
      "Standard configurations don't fit every mission. The Custom Build Program is a consultative engagement where we work with you to design, source, and build a cyberdeck tailored to your exact requirements.\n\nFrom specialized I/O configurations to custom OS imaging, team-scale deployments to bespoke form factors — we handle the complexity so you can focus on the work. Minimum order: 1 unit. Volume pricing available for 3+.",
    startingPrice: null,
    specs: [
      "Tailored hardware specification",
      "Custom OS imaging and hardening",
      "Branding and aesthetic options",
      "Specialized I/O configurations",
      "Bulk order support (3+ units)",
      "Full documentation and provisioning guides",
    ],
    features: [
      "Consultative scoping and requirements gathering",
      "Hardware selection and sourcing",
      "Custom OS imaging and software configuration",
      "Team-scale deployment and provisioning support",
      "Optional white-label and branding",
      "Ongoing support and maintenance programs",
    ],
    useCases: [
      "Team and organizational deployments",
      "Research environments with specialized needs",
      "Training and lab kit provisioning",
      "Industrial or specialized field use cases",
      "OEM and white-label programs",
    ],
    images: [],
    featured: true,
    available: true,
    preorderOnly: false,
  },
]

export function getProductBySlug(slug: string): Product | undefined {
  return products.find((p) => p.slug === slug)
}

export function getFeaturedProducts(): Product[] {
  return products.filter((p) => p.featured)
}

export function getRelatedProducts(currentSlug: string): Product[] {
  return products.filter((p) => p.slug !== currentSlug).slice(0, 2)
}
