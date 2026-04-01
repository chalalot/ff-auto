import * as React from 'react'
import { cn } from '@/lib/utils'

// Simple HTML range input fallback (no @radix-ui/react-slider needed)
export const Slider = React.forwardRef<
  HTMLInputElement,
  {
    value?: number[]
    min?: number
    max?: number
    step?: number
    onValueChange?: (value: number[]) => void
    className?: string
    disabled?: boolean
  }
>(({ value, min = 0, max = 100, step = 1, onValueChange, className, disabled }, ref) => (
  <input
    ref={ref}
    type="range"
    min={min}
    max={max}
    step={step}
    value={value?.[0]}
    disabled={disabled}
    onChange={(e) => onValueChange?.([parseFloat(e.target.value)])}
    className={cn('w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary', className)}
  />
))
Slider.displayName = 'Slider'
