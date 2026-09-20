"use client";

import { useEffect } from "react";

import { WsMessage } from "@/lib/types";

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  useEffect(() => {
    const configured = process.env.NEXT_PUBLIC_WS_URL;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = configured || `${protocol}//${window.location.hostname}:8000/ws/alerts`;
    const ws = new WebSocket(url);
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
