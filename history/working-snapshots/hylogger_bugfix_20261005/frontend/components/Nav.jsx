"use client";

// Top bar: brand, the three views, and live counts from the API.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCatalogue } from "@/lib/useCatalogue";

const VIEWS = [
  { href: "/", label: "Explore" },
  { href: "/compare", label: "Compare" },
  { href: "/viewer3d", label: "3D" },
];

export default function Nav() {
  const pathname = usePathname();
  const { holes, loading, error } = useCatalogue();

  return (
    <header className="topbar">
      <div className="brand">
        GSWA <span>HyLogger</span> Explorer
      </div>

      <nav className="nav">
        {VIEWS.map((view) => (
          <Link
            key={view.href}
            href={view.href}
            className={pathname === view.href ? "active" : ""}
          >
            {view.label}
          </Link>
        ))}
      </nav>

      {!loading && !error && (
        <div className="topbar-stats">
          <span>holes <b>{holes.length.toLocaleString()}</b></span>
        </div>
      )}
    </header>
  );
}
