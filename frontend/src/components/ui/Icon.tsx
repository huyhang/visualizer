// A small set of line icons, drawn inline so the studio loads nothing else.

const PATHS = {
  plus: "M12 5v14M5 12h14",
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6L6 18",
  chevronRight: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  arrowUp: "M12 19V5M6 11l6-6 6 6",
  arrowDown: "M12 5v14M6 13l6 6 6-6",
  send: "M5 12h13M13 6l6 6-6 6",
  sparkle:
    "M12 3c.6 3.7 1.9 5 5.6 5.6-3.7.6-5 1.9-5.6 5.6-.6-3.7-1.9-5-5.6-5.6C10.1 8 11.4 6.7 12 3zM18.5 14.5c.3 1.8.9 2.4 2.5 2.7-1.6.3-2.2.9-2.5 2.6-.3-1.7-.9-2.3-2.5-2.6 1.6-.3 2.2-.9 2.5-2.7z",
  deeper: "M4 6h10M4 12h7M4 18h4M17 9v10M13.5 15.5L17 19l3.5-3.5",
  steer: "M4 7h9M17 7h3M4 17h3M11 17h9M15 4v6M9 14v6",
  note: "M7 3.5h7.5L19 8v12.5H7zM14 3.5V8h5M10 12.5h6M10 16h6",
  image: "M4 5h16v14H4zM4 15l4.5-4.5 4 4 2.5-2.5L20 17M15.5 9.5h.01",
  link: "M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1",
  external: "M14 4h6v6M20 4l-9 9M18 14v5H5V6h5",
  alert: "M12 4l9 16H3zM12 10v4M12 17h.01",
  trash: "M5 7h14M9 7V4.5h6V7M7 7l1 13h8l1-13",
  stop: "M7 7h10v10H7z",
  shield: "M12 3l7 3v6c0 4-3 7.5-7 9-4-1.5-7-5-7-9V6zM9 12l2 2 4-4",
  ban: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM5.6 5.6l12.8 12.8",
  edit: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  eye: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  book: "M5 4.5h9a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3zM17 19.5h2V6.5",
  dots: "M6 12h.01M12 12h.01M18 12h.01",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  layers: "M12 4l9 5-9 5-9-5zM3 14l9 5 9-5",
  undo: "M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  redo: "M15 14l5-5-5-5M20 9H9.5a5.5 5.5 0 0 0 0 11H13",
  list: "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01",
  listOrdered:
    "M10 6h10M10 12h10M10 18h10M4 4.5h1.5V9M4 9h3M4 14.5c.5-.7 2.8-.9 2.8.6 0 1.2-2.8 2.1-2.8 3.4h3",
  menu: "M4 7h16M4 12h16M4 17h16",
  panel: "M4 5h16v14H4zM15 5v14",
  message: "M5 5h14v10H10l-4 4v-4H5z",
  arrowLeft: "M19 12H5M11 6l-6 6 6 6",
  history: "M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4M12 8v4.5l3 2",
  quote:
    "M7 16c-1.7 0-3-1.3-3-3 0-2.7 2-5 4.5-6M17 16c-1.7 0-3-1.3-3-3 0-2.7 2-5 4.5-6M7 10a3 3 0 1 1 0 6M17 10a3 3 0 1 1 0 6",
  draft: "M6 3.5h8l4 4v13H6zM14 3.5v4h4M9 12h6M9 15.5h4",
  star: "M12 4l2.4 5 5.4.6-4 3.7 1.1 5.3L12 16l-4.9 2.6 1.1-5.3-4-3.7 5.4-.6z",
  compare: "M8 4v16M16 4v16M4 8l4-4 4 4M12 16l4 4 4-4",
  rename: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  settings:
    "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  branch: "M6 4v16M6 8c0 4 12 2 12 8v4M18 4v4",
  map: "M9 4L3 6.5v13.5L9 17.5l6 2.5 6-2.5V4l-6 2.5zM9 4v13.5M15 6.5V20",
  target:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM12 11.5h.01",
  calendar: "M4.5 6h15v14h-15zM4.5 10.5h15M8.5 3.5v4M15.5 3.5v4",
  scenes: "M4 5h16v14H4zM4 9.5h16M9 5v4.5M15 5v4.5",
  user: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4.5 20.5c1-3.6 4-5.5 7.5-5.5s6.5 1.9 7.5 5.5",
  pin: "M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  grip: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
  lens: "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM20 20l-4.8-4.8M8 10.5h5M10.5 8v5",
  command: "M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z",
  gem: "M6 4h12l3 5-9 11L3 9zM3 9h18M9 4l3 16M15 4l-3 16",
  home: "M4 11l8-7 8 7M6 9.5V20h12V9.5",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="st-icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
