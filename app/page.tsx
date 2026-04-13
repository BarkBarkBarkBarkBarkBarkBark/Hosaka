import Hero from "@/components/sections/Hero"
import ValueProp from "@/components/sections/ValueProp"
import FeaturedProducts from "@/components/sections/FeaturedProducts"
import WhyUs from "@/components/sections/WhyUs"
import UseCases from "@/components/sections/UseCases"
import LeadCaptureCTA from "@/components/sections/LeadCaptureCTA"

export default function HomePage() {
  return (
    <>
      <Hero />
      <ValueProp />
      <FeaturedProducts />
      <WhyUs />
      <UseCases />
      <LeadCaptureCTA />
    </>
  )
}
