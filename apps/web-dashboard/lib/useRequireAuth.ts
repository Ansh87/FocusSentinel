"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "./api";

/**
 * Guards a protected page against an unauthenticated visitor. The real
 * security boundary is the API's own auth checks (every endpoint requires a
 * valid bearer token and is scoped server-side to the caller's own
 * family/student/rules -- see deps.py) -- this hook is purely a frontend UX
 * fix: without it, a signed-out visitor hitting /dashboard directly would
 * briefly see an empty page with a working "Sign out" button before every
 * API call failed one by one. Instead, redirect to sign-in immediately,
 * before any protected content or API calls fire.
 *
 * Usage: `const authOk = useRequireAuth(); if (!authOk) return null;` as the
 * very first thing in a protected page component.
 */
export function useRequireAuth(): boolean {
  const router = useRouter();
  const [authOk, setAuthOk] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/?expired=1");
      return;
    }
    setAuthOk(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return authOk;
}
