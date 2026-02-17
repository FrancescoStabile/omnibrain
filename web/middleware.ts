/**
 * Next.js middleware — injects the OmniBrain API auth token into
 * all /api/* requests before they are proxied to the backend via rewrites.
 *
 * The token is read from the OMNIBRAIN_API_KEY environment variable,
 * which is set by run.sh from ~/.omnibrain/auth_token.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const apiKey = process.env.OMNIBRAIN_API_KEY;

  if (apiKey && request.nextUrl.pathname.startsWith("/api/")) {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("X-API-Key", apiKey);

    return NextResponse.next({
      request: { headers: requestHeaders },
    });
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
