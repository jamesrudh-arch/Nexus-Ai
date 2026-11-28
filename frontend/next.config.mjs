/**
 * The dashboard talks to the API through relative paths, and this file is where they are turned into
 * a real backend URL.
 *
 * That indirection is not cosmetic. The browser never learns where the API lives: it requests
 * `/api/v1/paper/account`, and the Next server — which does know — forwards it. In the sandboxed
 * preview the browser and the API are on different hosts, so a page that fetched
 * `http://localhost:8000` would fail in exactly the environment it is meant to be demonstrated in.
 * It also keeps the API origin out of the client bundle, so moving the backend changes an
 * environment variable rather than a rebuild.
 *
 * `allowedDevOrigins` names the preview host pattern so the dev server accepts cross-origin requests
 * for it instead of refusing them, which is the other half of the same problem.
 */

const API_TARGET = process.env.NEXUS_API_URL ?? "http://127.0.0.1:8000";
const PORT = process.env.PORT ?? "3000";

/**
 * The label the UI prints, with any credential stripped.
 *
 * `NEXT_PUBLIC_` values are inlined into the client bundle, so exposing the target verbatim would
 * publish a password to every browser that loads the dashboard if anyone ever set a URL of the form
 * `https://user:pass@host`. The backend already refuses to do this to a database DSN
 * (`store/pg.py: public_dsn`); the same rule applies here, and for the same reason.
 */
function publicLabel(target) {
  try {
    const url = new URL(target);
    url.username = "";
    url.password = "";
    return url.toString().replace(/\/$/, "");
  } catch {
    // Not a URL (a relative base, say). Nothing to redact, and guessing would be worse.
    return target;
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  allowedDevOrigins: [
    `localhost:${PORT}`,
    `127.0.0.1:${PORT}`,
    "*.e2b.app",
    "*.arena.ai",
  ],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_TARGET}/:path*`,
      },
    ];
  },
  env: {
    // Exposed to the client on purpose, and it carries no secret: it is the label the UI prints so
    // an operator can see which backend a dashboard is pointed at. The URL itself stays server-side.
    NEXT_PUBLIC_API_LABEL: process.env.NEXT_PUBLIC_API_LABEL ?? publicLabel(API_TARGET),
  },
};

export default nextConfig;
