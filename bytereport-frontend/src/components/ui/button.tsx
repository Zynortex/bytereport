import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // The primary button (the default variant: a CTA, "New analysis", sign-up)
  // is the one solid accent fill on a page, with dark ink on it. Every other
  // variant is a 1px stroke with an uppercase label.
  // The press settles to 0.98 (--press-scale) and back: it arrives, it never
  // overshoots. Hover brightens the frame. Durations are the --dur-* tokens
  // (design-tokens.json → motion); under reduced motion the global rule makes
  // both instant.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xs text-xs label-caps transition-[color,background-color,border-color,transform] duration-[var(--dur-press)] ease-out active:scale-[var(--press-scale)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 disabled:active:scale-100",
  {
    variants: {
      variant: {
        // Accent fill, accent-ink label (10.97:1); hover lifts to the soft accent.
        default:     "border border-accent bg-accent text-accent-ink hover:bg-accent-soft hover:border-accent-soft active:bg-accent-soft",
        destructive: "border border-sev-high bg-transparent text-sev-high-fg hover:bg-sev-high/12 active:bg-sev-high/25",
        outline:     "border border-brand-border bg-transparent text-brand-dark hover:border-accent-fg hover:text-accent-fg active:bg-accent/15",
        secondary:   "border border-brand-border bg-transparent text-brand-muted hover:text-brand-dark hover:border-brand-muted active:bg-line/60",
        ghost:       "text-brand-muted hover:text-brand-dark active:bg-line/60",
        link:        "text-accent-fg underline-offset-4 hover:underline",
        danger:      "border border-sev-high bg-transparent text-sev-high-fg hover:bg-sev-high/12 active:bg-sev-high/25",
      },
      // Below md every size is at least 44px tall: a finger, not a cursor.
      size: {
        default: "h-10 max-md:h-11 px-4 py-2",
        sm:      "h-8 max-md:h-11 rounded-xs px-3 text-[11px]",
        lg:      "h-12 rounded-xs px-8 text-xs",
        icon:    "h-10 w-10 max-md:h-11 max-md:w-11",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    if (asChild) {
      return (
        <Slot
          className={cn(buttonVariants({ variant, size, className }))}
          ref={ref}
          {...props}
        >
          {children}
        </Slot>
      );
    }
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 size={14} className="animate-spin shrink-0" />}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
