/**
 * frontend/src/types/next-auth.d.ts
 * task: data-045
 *
 * Extends NextAuth's built-in types to include the backend_token and id
 * fields that our auth-config.ts attaches to the session.
 */

import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    user: {
      id?: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
      /** JWT from our FastAPI backend — attach as Bearer token for API calls. */
      backend_token?: string;
    };
  }

  interface User {
    backend_token?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    /** Our FastAPI JWT, stored in the NextAuth cookie for API calls. */
    backend_token?: string;
  }
}
