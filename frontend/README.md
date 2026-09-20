# SYN frontend

The Next.js interface for the local SYN prototype. Start the backend and its PostgreSQL, Qdrant and Redis services as described in the [root README](../README.md), then run `npm ci && npm run dev` here. `npm run lint`, `npm run typecheck` and `npm run build` are the frontend checks.

The `/api` rewrite targets `http://localhost:8000` by default. Set `NEXT_PUBLIC_API_URL` for another backend address at build time. WebSocket alerts target port 8000 on the browser's current host by default; set `NEXT_PUBLIC_WS_URL` to an explicit `ws://` or `wss://` URL when needed.
