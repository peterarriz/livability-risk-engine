"use client";

import { useEffect } from "react";

export function ScrollNavState() {
  useEffect(() => {
    const update = () => {
      document.body.dataset.navCompact = window.scrollY > 24 ? "1" : "0";
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return null;
}
