import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Executive Admin · Bishnoi One",
    short_name: "Exec Admin",
    description: "Corporate services: requests, assets, fleet, compliance, travel, contracts and banking.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    display_override: ["window-controls-overlay", "standalone"],
    orientation: "any",
    background_color: "#fafafa",
    theme_color: "#f2f2f2",
    categories: ["business", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Raise a Concern", url: "/me/raise-concern", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Request Supplies", url: "/me/request-supplies", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "My Requests", url: "/me/requests", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
