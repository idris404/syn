"use client";

import { useCallback, useState } from "react";

export type ToastItem = {
  id: string;
  title: string;
  description?: string;
};

export function useToastStore() {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((item: Omit<ToastItem, "id">) => {
    const id = crypto.randomUUID();
    setItems((prev) => [...prev, { ...item, id }]);
    setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return { items, toast, setItems };
}
