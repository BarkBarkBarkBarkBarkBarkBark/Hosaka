PROJECT: Cyberdeck e-commerce and marketing website
TARGET: Deploy on Vercel
GOAL: Build the first production-ready version of a web platform that markets, explains, and sells portable cyberdecks. The site should feel modern, technical, and premium, while staying simple enough to launch quickly.

PRIMARY OBJECTIVE:
Create a performant, mobile-friendly website that:
1. Markets cyberdeck products
2. Explains the value proposition clearly
3. Captures leads and preorder interest
4. Supports product listings and future checkout integration
5. Is structured as the foundation for a larger platform later

TECH STACK REQUIREMENTS:
- Framework: Next.js (App Router)
- Language: TypeScript
- Styling: Tailwind CSS
- Deployment target: Vercel
- Component style: clean, reusable, minimal
- Content source: local static content for now
- State management: keep lightweight, React state only unless truly needed
- Forms: simple server actions or API route stubs
- Images: use Next/Image
- Icons: lucide-react
- Animations: subtle only, framer-motion if needed
- SEO: include metadata, Open Graph, Twitter cards, sitemap-ready structure
- Accessibility: semantic HTML, keyboard navigable, reasonable contrast
- Performance: prioritize Lighthouse-friendly implementation

BRAND DIRECTION:
Brand theme:
- premium cyberpunk meets practical field tool
- not a toy
- not gamer-centric
- should appeal to developers, security researchers, tinkerers, field operators, and technical enthusiasts

Tone:
- sharp
- technical
- trustworthy
- slightly futuristic
- clear and conversion-oriented

Avoid:
- cringe hacker clichés
- excessive neon everywhere
- gimmicky terminal overload
- unreadable low-contrast UI

VISUAL DIRECTION:
- dark theme by default
- strong typography
- restrained accent color (electric blue, muted green, or amber)
- grid-based layout
- rounded cards
- premium landing page feel
- product-forward design
- allow room for product renders/photos later
- subtle animated background accents are okay if performance stays good

SITE ARCHITECTURE:
Build these routes/pages:

1. Home page
   Purpose:
   - explain what the company is
   - show hero section
   - show flagship cyberdeck offering
   - establish trust
   - capture email interest / preorder

   Sections:
   - hero
   - value proposition
   - featured product cards
   - “why our cyberdecks” section
   - use cases
   - lead capture CTA
   - footer

2. Products page
   Purpose:
   - show current product lineup
   - support 3 initial SKUs

   Initial SKUs:
   - Field Deck Lite
   - Operator Deck
   - Custom Build Program

   Each product card should include:
   - product name
   - short description
   - starting price or “starting at”
   - key specs
   - CTA button

3. Product detail page
   Dynamic route for individual products:
   /products/[slug]

   Include:
   - product hero
   - gallery placeholder
   - overview
   - key specs
   - ideal user
   - preorder CTA
   - FAQ
   - related products

4. About page
   Purpose:
   - explain the mission
   - position the company as building portable technical systems
   - emphasize design, portability, and preconfiguration

5. Contact page
   Include:
   - simple contact form
   - business inquiry / custom build inquiry
   - social/contact placeholders

6. Preorder / interest page
   Purpose:
   - capture customer interest before full checkout is live
   Include:
   - form for name, email, company/organization, product interest, use case, budget range
   - success state
   - backend stub for future integration

7. Optional placeholder pages
   - /faq
   - /terms
   - /privacy

DATA MODEL:
Create a local typed data source for products.
Use a structure like:
- slug
- name
- tagline
- shortDescription
- longDescription
- startingPrice
- specs
- features
- useCases
- images
- featured
- available
- preorderOnly

Seed with these products:

1. Field Deck Lite
   tagline: Entry portable cyberdeck for fast deployment
   shortDescription: A low-cost, preconfigured cyberdeck built for mobile computing, experimentation, and field-ready workflows.
   startingPrice: 349
   specs:
   - Raspberry Pi based compute
   - Portable display
   - Compact keyboard
   - Battery-powered operation
   - Preconfigured software environment
   useCases:
   - portable lab setup
   - networking toolkit
   - security research
   - field scripting and diagnostics

2. Operator Deck
   tagline: Ruggedized portable workstation
   shortDescription: A more capable cyberdeck designed for demanding users who want more power, durability, and upgrade paths.
   startingPrice: 699
   specs:
   - upgraded compute
   - larger battery
   - improved display
   - enhanced I/O
   - modular accessory support

3. Custom Build Program
   tagline: Built around your mission
   shortDescription: Custom cyberdeck design and configuration for teams, researchers, and specialized deployments.
   startingPrice: null
   specs:
   - tailored hardware
   - software imaging
   - branding options
   - specialized workflows
   - consultative build process

FEATURE REQUIREMENTS:
1. Landing page hero
   Must clearly communicate:
   - what cyberdecks are
   - why these are useful
   - why this company is different

   Hero copy direction:
   headline: Portable systems built for technical work
   subheadline: Preconfigured cyberdecks for developers, researchers, and field operators.
   CTAs:
   - Explore Products
   - Join Preorder List

2. Lead capture
   Build a reusable lead capture form component.
   For now:
   - validate client-side and server-side
   - store submissions in a simple mock handler or local logging stub
   - architect code so it can later swap to Resend, Formspree, Supabase, or Stripe-connected workflows

3. Product cards
   Build reusable product card component.

4. CTA sections
   Include multiple strong CTA blocks across the site.

5. FAQ accordion
   Reusable accordion for common product questions.

6. Navigation
   Responsive navbar with:
   - logo text placeholder
   - Home
   - Products
   - About
   - Contact
   - Preorder
   - mobile menu

7. Footer
   Include:
   - quick links
   - short brand summary
   - placeholder social links
   - copyright

COPY REQUIREMENTS:
Generate polished placeholder marketing copy throughout the site.
The copy should feel real, not lorem ipsum.

Messaging themes:
- portable computing
- field-ready systems
- preconfigured environments
- custom builds
- fast deployment
- technical credibility

Do not position products as illegal-use devices.
Keep messaging lawful and professional.
Focus on development, research, diagnostics, field operations, and technical workflows.

UX REQUIREMENTS:
- fully responsive
- strong mobile layout
- product cards stack nicely on small screens
- forms easy to complete on mobile
- sticky navbar okay if tasteful
- buttons should have clear hover/focus states

CODE QUALITY REQUIREMENTS:
- modular folder structure
- typed props
- small reusable components
- avoid giant monolithic files
- clean naming
- no dead code
- no placeholder garbage comments
- no unnecessary dependencies

SUGGESTED FOLDER ORGANIZATION:
- app/
- components/
- components/ui/
- lib/
- data/
- public/
- styles/

DELIVERABLES:
1. Working Next.js project ready for local dev
2. Clean README with:
   - setup
   - env vars
   - run locally
   - deploy to Vercel
3. Seed product data
4. Fully built pages listed above
5. Reusable components
6. Basic metadata/SEO implementation
7. Attractive default styling
8. Mock form submission flow
9. Placeholder legal pages
10. Sensible site structure for future expansion into full commerce

FUTURE-PROOFING:
Structure code so the project can later support:
- Stripe checkout
- user accounts
- CMS-backed product management
- blog/content marketing
- custom build intake workflows
- order tracking
- support portal

IMPLEMENTATION NOTES:
- prefer server components where appropriate
- use client components only when needed
- keep initial architecture simple
- no database required yet
- do not overengineer
- build a launchable v1

SUCCESS CRITERIA:
The result should look like a real startup landing site, not a tutorial project.
A visitor should immediately understand:
- what is being sold
- who it is for
- why it is valuable
- how to express purchase interest

FINAL TASK:
Generate the full project codebase for this v1 website, including all routes, components, styling, local data, and README, in a form ready to run and deploy on Vercel.