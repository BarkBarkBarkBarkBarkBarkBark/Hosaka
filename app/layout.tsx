import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import "./globals.css"
import Navbar from "@/components/layout/Navbar"
import Footer from "@/components/layout/Footer"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: {
    default: "CyberDeck — Portable Systems for Technical Work",
    template: "%s | CyberDeck",
  },
  description:
    "Premium preconfigured cyberdecks for developers, security researchers, and field operators. Ready to deploy out of the box.",
  keywords: [
    "cyberdeck",
    "portable computer",
    "raspberry pi",
    "field computer",
    "security research",
    "portable workstation",
    "linux deck",
  ],
  openGraph: {
    title: "CyberDeck — Portable Systems for Technical Work",
    description:
      "Preconfigured cyberdecks for developers, security researchers, and field operators.",
    url: "https://cyberdeck.io",
    siteName: "CyberDeck",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "CyberDeck — Portable Systems for Technical Work",
    description:
      "Preconfigured cyberdecks for developers, security researchers, and field operators.",
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} antialiased`}
    >
      <body className="bg-slate-950 text-slate-100 flex flex-col min-h-screen">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  )
}

