/**
 * Next.js configuration.
 *
 * `BACKEND_API_URL` is deliberately NOT exposed with a `NEXT_PUBLIC_` prefix. The
 * browser never talks to the API directly: it talks to this app's route handlers,
 * which hold the session cookie and forward the call server-side (ADR-0002). Publishing
 * the backend URL to the bundle would invite exactly the direct calls that design
 * avoids — and those calls cannot carry an HttpOnly cookie anyway.
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    typedRoutes: true,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
