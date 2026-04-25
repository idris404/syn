"use client";

import { Toast, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from "@/components/ui/toast";
import { ToastItem } from "@/components/ui/use-toast";

interface Props {
  items: ToastItem[];
}

export function Toaster({ items }: Props) {
  return (
    <ToastProvider>
      {items.map((item) => (
        <Toast key={item.id} open>
          <ToastTitle>{item.title}</ToastTitle>
          {item.description ? <ToastDescription>{item.description}</ToastDescription> : null}
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
