"use client"

import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

export interface AccordionItem {
  question: string
  answer: string
}

interface AccordionProps {
  items: AccordionItem[]
  className?: string
}

export default function Accordion({ items, className }: AccordionProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  return (
    <div className={cn("space-y-2", className)}>
      {items.map((item, index) => {
        const isOpen = openIndex === index
        return (
          <div
            key={index}
            className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/30 hover:border-slate-700 transition-colors"
          >
            <button
              className="w-full flex items-center justify-between px-6 py-4 text-left gap-4 cursor-pointer"
              onClick={() => setOpenIndex(isOpen ? null : index)}
              aria-expanded={isOpen}
            >
              <span className="font-medium text-slate-200 leading-snug">
                {item.question}
              </span>
              <ChevronDown
                className={cn(
                  "w-4 h-4 text-slate-500 shrink-0 transition-transform duration-200",
                  isOpen && "rotate-180"
                )}
              />
            </button>
            <div
              className={cn(
                "overflow-hidden transition-all duration-200",
                isOpen ? "max-h-96" : "max-h-0"
              )}
            >
              <p className="px-6 pb-5 text-slate-400 leading-relaxed text-sm">
                {item.answer}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
