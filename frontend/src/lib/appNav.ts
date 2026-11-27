// The app's primary navigation: ONE list used by the rail (desktop) and the tab bar (phone). Packages add their destination here (one line each),
// with a key in their own area's catalogue. `id` matches the `active` prop of AppLayout. Keep it to 5 items or fewer (tab bar).
export interface NavItem { id: string; href: string; key: string; icon: string }
// Icons are 24x24 outline paths (stroke 1.75, round), drawn inline so the shell needs no icon font.
export const APP_NAV: readonly NavItem[] = [
  { id: "videos", href: "/generations", key: "nav.videos", icon: "M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-11Zm6.5 2.8v5.4a.6.6 0 0 0 .9.5l4.4-2.7a.6.6 0 0 0 0-1l-4.4-2.7a.6.6 0 0 0-.9.5Z" },
  { id: "media", href: "/media", key: "media.nav_label", icon: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM4 16l4.5-4.5 4 4 3-3L20 17M9 9h.01" },
  { id: "new", href: "/new", key: "create.nav_label", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5v8M8 12h8" },
  { id: "credits", href: "/wallet", key: "nav.credits", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4.5v9m-2.6-6.7c0-.9 1.2-1.6 2.6-1.6s2.6.7 2.6 1.6-1.2 1.5-2.6 1.7-2.6.8-2.6 1.7 1.2 1.6 2.6 1.6 2.6-.7 2.6-1.6" },
  { id: "settings", href: "/settings", key: "settings.nav", icon: "M5 7h9m4 0h1M5 17h1m4 0h9M14 4.5v5M10 14.5v5" },
];
