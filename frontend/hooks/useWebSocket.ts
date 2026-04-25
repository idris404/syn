"use client";

import { useEffect } from "react";

import { WsMessage } from "@/lib/types";

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/alerts");
    ws.onmessage = (event) => {
      const msg: WsMessage = JSON.parse(event.data);
      if (msg.type !== "ping") onMessage(msg);
    };
    ws.onerror = () => {
      console.warn("WS error - alerts disabled");
    };
    return () => ws.close();
  }, [onMessage]);
}
