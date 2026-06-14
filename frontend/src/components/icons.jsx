// Orbit icon set — a tiny, dependency-free Lucide-style stroke icon library.
// One consistent visual system (1.8px stroke, round caps), tree-shakeable,
// and themeable via `currentColor`. Replaces the mixed react-icons usage.

function Svg({ size = 20, stroke = 2, className, style, label, children }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {children}
    </svg>
  );
}

export const Search = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </Svg>
);

export const ShoppingCart = (p) => (
  <Svg {...p}>
    <circle cx="8" cy="21" r="1" />
    <circle cx="19" cy="21" r="1" />
    <path d="M2.5 3h2l2.6 12.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.6L23 6H6" />
  </Svg>
);

export const Package = (p) => (
  <Svg {...p}>
    <path d="M11 21.7 3.6 17.6a1 1 0 0 1-.6-.9V7.3a1 1 0 0 1 .5-.9l7.5-4.1a1 1 0 0 1 1 0l7.5 4.1a1 1 0 0 1 .5.9v9.4a1 1 0 0 1-.5.9L13 21.7a2 2 0 0 1-2 0Z" />
    <path d="m3.3 7 8.7 5 8.7-5" />
    <path d="M12 22V12" />
  </Svg>
);

export const RotateCcw = (p) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
  </Svg>
);

export const MapPin = (p) => (
  <Svg {...p}>
    <path d="M20 10c0 5.5-8 12-8 12s-8-6.5-8-12a8 8 0 0 1 16 0Z" />
    <circle cx="12" cy="10" r="3" />
  </Svg>
);

export const ShieldCheck = (p) => (
  <Svg {...p}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
    <path d="m9 12 2 2 4-4" />
  </Svg>
);

export const Truck = (p) => (
  <Svg {...p}>
    <path d="M14 18V6a1 1 0 0 0-1-1H2a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h1" />
    <path d="M14 9h4l3 3v5a1 1 0 0 1-1 1h-1" />
    <circle cx="7" cy="18" r="2" />
    <circle cx="17" cy="18" r="2" />
  </Svg>
);

export const Recycle = (p) => (
  <Svg {...p}>
    <path d="M7 19H5a2 2 0 0 1-1.7-3l1.3-2.2" />
    <path d="m9 22 2-3-3-2" />
    <path d="M12.5 4.2 14 2l1.5 2.6 2.6 4.4" />
    <path d="m20 13 1.3 2.3a2 2 0 0 1-1.7 3H17" />
    <path d="M4.8 9.2 3.3 6.6A2 2 0 0 1 5 3.6h2.6" />
    <path d="m14 22 .9-3.3" />
  </Svg>
);

export const Store = (p) => (
  <Svg {...p}>
    <path d="M3 9.5 4.5 4h15L21 9.5" />
    <path d="M3 9.5a2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 3 0" />
    <path d="M4 11v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8" />
  </Svg>
);

export const Warehouse = (p) => (
  <Svg {...p}>
    <path d="M22 21V8.5a1 1 0 0 0-.6-.9l-9-3.9a1 1 0 0 0-.8 0l-9 3.9a1 1 0 0 0-.6.9V21" />
    <path d="M6 21V12h12v9" />
    <path d="M6 16h12" />
  </Svg>
);

export const ChevronRight = (p) => (
  <Svg {...p}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);

export const ChevronLeft = (p) => (
  <Svg {...p}>
    <path d="m15 6-6 6 6 6" />
  </Svg>
);

export const Star = (p) => (
  <Svg {...p}>
    <path d="m12 2.5 2.9 6 6.6.9-4.8 4.6 1.2 6.6L12 18.6 6.1 21.6l1.2-6.6L2.5 9.4l6.6-.9z" />
  </Svg>
);

export const Sprout = (p) => (
  <Svg {...p}>
    <path d="M7 20h10" />
    <path d="M12 20c0-7 0-9 0-9" />
    <path d="M12 11C12 7 9 5 4 5c0 5 3 7 8 7Z" />
    <path d="M12 11c0-3 2-5 6-5 0 4-2 6-6 6Z" />
  </Svg>
);

export const Gift = (p) => (
  <Svg {...p}>
    <rect x="3" y="8" width="18" height="4" rx="1" />
    <path d="M12 8v13" />
    <path d="M5 12v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8" />
    <path d="M12 8C12 8 11 3 8 3a2.5 2.5 0 0 0 0 5" />
    <path d="M12 8C12 8 13 3 16 3a2.5 2.5 0 0 1 0 5" />
  </Svg>
);

export const Activity = (p) => (
  <Svg {...p}>
    <path d="M3 12h4l3 8 4-16 3 8h4" />
  </Svg>
);

export const Check = (p) => (
  <Svg {...p}>
    <path d="M20 6 9 17l-5-5" />
  </Svg>
);

export const CheckCircle = (p) => (
  <Svg {...p}>
    <path d="M22 11.1V12a10 10 0 1 1-5.9-9.1" />
    <path d="m9 11 3 3L22 4" />
  </Svg>
);

export const AlertCircle = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 8v5" />
    <path d="M12 16h.01" />
  </Svg>
);

export const Info = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-5" />
    <path d="M12 8h.01" />
  </Svg>
);

export const Loader = (p) => (
  <Svg {...p}>
    <path d="M12 3a9 9 0 1 0 9 9" />
  </Svg>
);

export const Plus = (p) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const X = (p) => (
  <Svg {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
);

export const Menu = (p) => (
  <Svg {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </Svg>
);

export const LogOut = (p) => (
  <Svg {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="m16 17 5-5-5-5" />
    <path d="M21 12H9" />
  </Svg>
);

export const User = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M5.5 21a7 7 0 0 1 13 0" />
  </Svg>
);

export const Tag = (p) => (
  <Svg {...p}>
    <path d="M3 11V5a2 2 0 0 1 2-2h6l9 9a2 2 0 0 1 0 2.8l-5.2 5.2a2 2 0 0 1-2.8 0L3 11Z" />
    <circle cx="7.5" cy="7.5" r="1.2" />
  </Svg>
);

export const Leaf = (p) => (
  <Svg {...p}>
    <path d="M11 20A7 7 0 0 1 4 13c0-6 5-9 16-9 0 8-4 13-9 13Z" />
    <path d="M5 21c4-7 8-9 13-10" />
  </Svg>
);

export const Sparkles = (p) => (
  <Svg {...p}>
    <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z" />
    <path d="M19 14l.7 1.8L21.5 17l-1.8.7L19 19.5l-.7-1.8L16.5 17l1.8-.7z" />
  </Svg>
);

export const Mail = (p) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </Svg>
);

export const Calendar = (p) => (
  <Svg {...p}>
    <rect x="3" y="4.5" width="18" height="17" rx="2" />
    <path d="M8 2.5v4M16 2.5v4M3 9.5h18" />
  </Svg>
);
