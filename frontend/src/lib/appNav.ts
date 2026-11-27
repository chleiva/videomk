// The app's primary navigation: ONE list used by the rail (desktop) and the tab bar (phone). Packages add their destination here (one line each),
// with a key in their own area's catalogue. `id` matches the `active` prop of AppLayout. Keep it to 5 items or fewer (tab bar).
export interface NavItem { id: string; href: string; key: string; icon: string }
// Icons are 24x24 outline paths (stroke 1.75, round), drawn inline so the shell needs no icon font.
export const APP_NAV: readonly NavItem[] = [
  { id: "videos", href: "/generations", key: "nav.videos", icon: "M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-11Zm6.5 2.8v5.4a.6.6 0 0 0 .9.5l4.4-2.7a.6.6 0 0 0 0-1l-4.4-2.7a.6.6 0 0 0-.9.5Z" },
  { id: "credits", href: "/wallet", key: "nav.credits", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4.5v9m-2.6-6.7c0-.9 1.2-1.6 2.6-1.6s2.6.7 2.6 1.6-1.2 1.5-2.6 1.7-2.6.8-2.6 1.7 1.2 1.6 2.6 1.6 2.6-.7 2.6-1.6" },
  { id: "feedback", href: "/feedback", key: "nav.feedback", icon: "M5 5.5A2.5 2.5 0 0 1 7.5 3h9A2.5 2.5 0 0 1 19 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V16h-.5A2.5 2.5 0 0 1 4 13.5" },
];
