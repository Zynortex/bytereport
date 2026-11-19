import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 max-md:h-11 w-full rounded-xs border border-brand-border bg-transparent px-3 py-2 text-sm",
        // The focus state was a hard ring swap with nothing to ease it. The
        // border and the ring are separate properties, so both are named in the
        // transition — `transition-colors` alone would leave the ring snapping.
        "transition-[border-color] duration-200 ease-out",
        "placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg focus:ring-2 focus:ring-accent/30",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";

export { Input };
