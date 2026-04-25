import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function statusClass(status?: string | null) {
  const normalized = (status || "").toUpperCase();
  if (normalized === "RECRUITING") return "status-recruiting";
  if (normalized === "COMPLETED") return "status-completed";
  if (normalized === "ACTIVE_NOT_RECRUITING") return "status-active-not-recruiting";
  return "status-default";
}
