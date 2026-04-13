interface ProductSpecsProps {
  specs: string[]
  className?: string
}

export default function ProductSpecs({ specs, className = "" }: ProductSpecsProps) {
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 gap-3 ${className}`}>
      {specs.map((spec) => (
        <div
          key={spec}
          className="flex items-start gap-3 p-3 rounded-lg bg-slate-900/60 border border-slate-800"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500/60 shrink-0 mt-1.5" />
          <span className="text-sm text-slate-300 font-mono leading-snug">
            {spec}
          </span>
        </div>
      ))}
    </div>
  )
}
