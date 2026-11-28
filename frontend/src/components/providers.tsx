"use client";

/**
 * Client-side providers.
 *
 * TanStack Query owns data fetching (§3.5 rules it, and it is the reason no component calls
 * `fetch` directly): one cache, one retry policy, one place where "how stale is this?" is answered.
 * The query client is created inside state rather than at module scope because a module-level client
 * would be shared across requests during server rendering, which leaks one user's cache into
 * another's HTML.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // A trading screen is read every few seconds by someone who is watching it. Two seconds
            // is close enough to feel live and far enough from hammering an API that is also doing
            // ingestion work.
            refetchInterval: 2000,
            refetchOnWindowFocus: true,
            staleTime: 1000,
            retry: 2,
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
          },
          mutations: { retry: 0 },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
