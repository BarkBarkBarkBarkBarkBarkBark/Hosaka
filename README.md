# CyberDeck

Portable computing systems built for technical professionals. This is the v1 marketing and pre-commerce website, built with Next.js 16, TypeScript, and Tailwind CSS.

## Tech Stack

- **Framework:** Next.js 16 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS v4
- **Icons:** lucide-react
- **Animations:** framer-motion
- **Deployment:** Vercel

## Getting Started

### Prerequisites

- Node.js 20+
- npm 10+

### Install dependencies

```bash
npm install
```

### Set up environment variables

```bash
cp .env.example .env.local
```

Edit `.env.local` and fill in any required values. For local development, defaults work without changes.

### Run locally

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build for production

```bash
npm run build
npm run start
```

## Project Structure

```
app/                    # Next.js App Router pages
├── layout.tsx          # Root layout (Navbar + Footer)
├── page.tsx            # Home page
├── sitemap.ts          # Auto-generated sitemap
├── robots.ts           # robots.txt
├── products/
│   ├── page.tsx        # Product listing
│   └── [slug]/
│       └── page.tsx    # Product detail (dynamic)
├── about/page.tsx
├── contact/
│   ├── page.tsx
│   └── ContactForm.tsx  # Client form component
├── preorder/
│   ├── page.tsx
│   └── PreorderForm.tsx # Client form component
├── faq/page.tsx
├── terms/page.tsx
└── privacy/page.tsx

components/
├── layout/
│   ├── Navbar.tsx       # Sticky responsive navbar
│   └── Footer.tsx       # Site footer
├── ui/
│   ├── Button.tsx       # Reusable button (primary/secondary/ghost)
│   ├── Badge.tsx        # Status badge
│   └── Accordion.tsx    # FAQ accordion
├── sections/            # Home page sections
│   ├── Hero.tsx
│   ├── ValueProp.tsx
│   ├── FeaturedProducts.tsx
│   ├── WhyUs.tsx
│   ├── UseCases.tsx
│   └── LeadCaptureCTA.tsx
└── product/
    ├── ProductCard.tsx  # Product card for listings
    └── ProductSpecs.tsx # Spec grid display

data/
└── products.ts          # Typed product data + helper functions

lib/
├── utils.ts             # cn(), formatPrice()
└── actions.ts           # Server actions for form handling
```

## Pages

| Route | Description |
|---|---|
| `/` | Home — hero, value prop, products, use cases, lead capture |
| `/products` | Product listing |
| `/products/[slug]` | Product detail with specs, FAQ, related |
| `/about` | Company story and values |
| `/contact` | Contact form |
| `/preorder` | Preorder interest form |
| `/faq` | Full FAQ with accordion |
| `/terms` | Terms of Service |
| `/privacy` | Privacy Policy |

## Form Handling

Forms use Next.js Server Actions (`lib/actions.ts`). Submissions are currently logged to console. To connect a real email service:

1. Install your email library (e.g., `npm install resend`)
2. Add your API key to `.env.local`
3. Replace the `console.log` stubs in `lib/actions.ts` with real send calls

The form architecture supports Resend, Formspree, Supabase, or any server-side handler.

## Deploy to Vercel

### One-click deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/yourusername/cyber_deck)

### Manual deploy

1. Push your code to a GitHub/GitLab/Bitbucket repository
2. Import the project at [vercel.com/new](https://vercel.com/new)
3. Add environment variables from `.env.example` as needed
4. Deploy

Vercel automatically handles build, preview deployments, and production. No additional configuration required.

## Adding Products

Edit `data/products.ts`. Each product follows the `Product` interface defined at the top of the file. The site will automatically pick up new products in listings, the sitemap, and static params for the detail page.

## Future Roadmap

The codebase is structured to support:

- **Stripe checkout** — add payment routes in `app/checkout/`
- **CMS integration** — replace `data/products.ts` with Contentful / Sanity / Payload fetches
- **User accounts** — add auth via NextAuth or Clerk
- **Blog / content** — add `app/blog/` with MDX or CMS-sourced posts
- **Order tracking** — add order status routes once fulfillment is integrated
- **Support portal** — add ticket system or integrate Intercom/Zendesk

## License

Private. All rights reserved.
