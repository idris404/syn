import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, ...props }, ref) => {
    return (
      <input
        className={cn(
          "h-10 w-full rounded-md border border-[var(--syn-border)] bg-[#0f1018] px-3 py-2 text-sm text-[var(--syn-text)] placeholder:text-[var(--syn-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--syn-accent)]",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
