"use client";

// Spectrum design system — light cream paper, six considered colors,
// DM Sans + JetBrains Mono. Ported from M.I.R.A. Spectrum.html.

import { useEffect } from "react";

export const S = {
  bg: "#f7f5f0",
  surface: "#ffffff",
  surfaceHi: "#f4f1ea",
  surfaceTop: "#ebe6dc",
  glow: "rgba(234,74,22,0.06)",

  border: "rgba(12,13,17,0.08)",
  borderHi: "rgba(12,13,17,0.14)",
  borderHot: "rgba(12,13,17,0.22)",

  text: "#1a1614",
  text2: "rgba(26,22,20,0.68)",
  text3: "rgba(26,22,20,0.44)",
  text4: "rgba(26,22,20,0.24)",
  textInv: "#ffffff",

  coral: "#ff7a4a",
  coralSoft: "rgba(255,122,74,0.12)",
  coralLine: "rgba(255,122,74,0.36)",

  azure: "#2563eb",
  azureSoft: "rgba(37,99,235,0.10)",
  mint: "#16a34a",
  mintSoft: "rgba(22,163,74,0.10)",
  amber: "#c4750a",
  amberSoft: "rgba(196,117,10,0.10)",
  violet: "#7c3aed",
  violetSoft: "rgba(124,58,237,0.10)",
  rose: "#dc2626",
  roseSoft: "rgba(220,38,38,0.10)",

  pos: "#16a34a",
  neg: "#dc2626",

  fSans: 'var(--font-dm-sans), "DM Sans", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif',
  fMono: 'var(--font-jetbrains-mono), "JetBrains Mono", ui-monospace, "SF Mono", monospace',
} as const;

export type EventKind = "plan" | "tool" | "reflect" | "replan" | "synth" | "done";

export const KIND_COLORS: Record<EventKind, { c: string; bg: string; label: string }> = {
  plan: { c: S.azure, bg: S.azureSoft, label: "plan" },
  tool: { c: S.mint, bg: S.mintSoft, label: "tool" },
  reflect: { c: S.amber, bg: S.amberSoft, label: "reflect" },
  replan: { c: S.coral, bg: S.coralSoft, label: "replan" },
  synth: { c: S.violet, bg: S.violetSoft, label: "synth" },
  done: { c: S.text, bg: "rgba(255,255,255,0.05)", label: "done" },
};

const SPECTRUM_CSS = `
  .sp-page {
    background: ${S.bg};
    color: ${S.text};
    font-family: ${S.fSans};
    -webkit-font-smoothing: antialiased;
    letter-spacing: -0.01em;
    font-feature-settings: "ss01", "cv11", "cv05";
  }
  .sp { color: ${S.text}; font-family: ${S.fSans}; }
  .sp-mono { font-family: ${S.fMono}; font-feature-settings: "tnum", "ss01"; letter-spacing: 0; }
  .sp-num  { font-family: ${S.fMono}; font-variant-numeric: tabular-nums; letter-spacing: 0; }
  .sp-eyebrow {
    font-family: ${S.fMono};
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: ${S.text3};
  }
  .sp-h1 { font-size: 72px; font-weight: 600; letter-spacing: -0.025em; line-height: 1.02; margin: 0; }
  .sp-card { background: ${S.surface}; border: 1px solid ${S.border}; border-radius: 14px; }
  @keyframes sp-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(0.88); } }
  @keyframes sp-blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }
  @keyframes sp-shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
  .sp-pulse { animation: sp-pulse 1.6s ease-in-out infinite; }
  .sp-caret { display: inline-block; width: 2px; height: 1em; background: ${S.coral}; margin-left: 2px; vertical-align: -0.1em; animation: sp-blink 1.05s steps(2) infinite; }
  .sp-shimmer {
    background: linear-gradient(90deg, rgba(0,0,0,0.04) 0%, rgba(0,0,0,0.10) 50%, rgba(0,0,0,0.04) 100%);
    background-size: 200% 100%;
    animation: sp-shimmer 2s ease-in-out infinite;
    border-radius: 3px;
  }
  .sp-page ::-webkit-scrollbar { width: 8px; height: 8px; }
  .sp-page ::-webkit-scrollbar-track { background: transparent; }
  .sp-page ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.10); border-radius: 4px; }
  .sp-page ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.20); }
  @media print {
    @page { size: A4; margin: 14mm 12mm; }
    html, body { background: white !important; }
    .sp-no-print, .sp-pulse, .sp-caret { display: none !important; animation: none !important; }
    .sp-page { background: white !important; min-height: 0 !important; }
    .sp-page > div[style*="radial-gradient"] { display: none !important; }
    .sp-page header, .sp-page aside, .sp-page footer { display: none !important; }
    /* Collapse the two-column report grid into one continuous column */
    .sp-page > div > div[style*="grid-template-columns"] {
      display: block !important;
      padding: 0 !important;
    }
    .sp-page main { display: block !important; }
    .sp-page main > section,
    .sp-page main > div[style*="border-radius"] {
      page-break-inside: avoid;
      break-inside: avoid;
      margin: 0 0 12mm 0 !important;
      box-shadow: none !important;
      background: white !important;
      border: 1px solid #e5e2dc !important;
    }
    .sp-page section { background: white !important; }
    .sp-page h1 { font-size: 36pt !important; line-height: 1.05 !important; white-space: normal !important; }
    .sp-page [class*="sticky"] { position: static !important; }
    /* Hero block: tighten and let the page flow into the report */
    .sp-page section[style*="padding: 48px"] { padding: 0 0 8mm 0 !important; }
    /* Print header injected by the body */
    .sp-print-header {
      display: block !important;
      padding: 0 0 6mm 0;
      margin: 0 0 6mm 0;
      border-bottom: 2px solid #1a1614;
      font-family: ${S.fSans};
    }
  }
  .sp-print-header { display: none; }
`;

export function SpectrumGlobals() {
  useEffect(() => {
    if (document.getElementById("spectrum-globals")) return;
    const s = document.createElement("style");
    s.id = "spectrum-globals";
    s.textContent = SPECTRUM_CSS;
    document.head.appendChild(s);
  }, []);
  return null;
}

type CSS = React.CSSProperties;

export function Eyebrow({
  children,
  serial,
  color,
  style,
}: {
  children?: React.ReactNode;
  serial?: string;
  color?: string;
  style?: CSS;
}) {
  return (
    <div className="sp-eyebrow" style={{ color: color ?? S.text3, ...style }}>
      {serial && <span style={{ color: S.coral, marginRight: 8 }}>{serial}</span>}
      {children}
    </div>
  );
}

export function Tag({
  children,
  color,
  solid,
  style,
  dot,
}: {
  children?: React.ReactNode;
  color?: string;
  solid?: boolean;
  style?: CSS;
  dot?: boolean;
}) {
  const c = color ?? S.text2;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontFamily: S.fMono,
        fontSize: 10,
        fontWeight: 500,
        letterSpacing: 0.5,
        textTransform: "uppercase",
        padding: "4px 9px 3px",
        borderRadius: 999,
        background: solid ? c : `${c}1a`,
        color: solid ? S.textInv : c,
        border: solid ? "none" : `1px solid ${c}3a`,
        whiteSpace: "nowrap",
        lineHeight: 1.3,
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: solid ? S.textInv : c,
          }}
        />
      )}
      {children}
    </span>
  );
}

type BtnProps = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "style"> & {
  primary?: boolean;
  ghost?: boolean;
  small?: boolean;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  style?: CSS;
};

export function Btn({
  children,
  primary,
  ghost,
  small,
  icon,
  iconRight,
  style,
  ...rest
}: BtnProps) {
  return (
    <button
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        font: "inherit",
        fontFamily: S.fSans,
        fontSize: small ? 13 : 14,
        fontWeight: 500,
        letterSpacing: -0.1,
        padding: small ? "7px 14px" : "11px 22px",
        background: primary ? S.coral : ghost ? "transparent" : S.surfaceHi,
        color: primary ? S.textInv : S.text,
        border: ghost ? `1px solid ${S.border}` : "none",
        borderRadius: 10,
        cursor: "pointer",
        transition: "transform .12s, background .12s",
        ...style,
      }}
      {...rest}
    >
      {icon}
      {children}
      {iconRight}
    </button>
  );
}

export function Stat({
  label,
  value,
  delta,
  deltaColor,
  sub,
  size = 28,
  align = "left",
  style,
}: {
  label: string;
  value: React.ReactNode;
  delta?: string;
  deltaColor?: string;
  sub?: string;
  size?: number;
  align?: "left" | "right";
  style?: CSS;
}) {
  const dColor =
    deltaColor ??
    (delta?.startsWith("+") ? S.pos : delta?.startsWith("−") ? S.neg : S.text3);
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        textAlign: align,
        ...style,
      }}
    >
      <Eyebrow>{label}</Eyebrow>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 8,
          justifyContent: align === "right" ? "flex-end" : "flex-start",
          whiteSpace: "nowrap",
        }}
      >
        <span
          className="sp-num"
          style={{
            fontSize: size,
            fontWeight: 500,
            color: S.text,
            letterSpacing: "-0.02em",
          }}
        >
          {value}
        </span>
        {delta && (
          <span
            className="sp-num"
            style={{
              fontSize: Math.max(11, size - 14),
              color: dColor,
              fontWeight: 500,
            }}
          >
            {delta}
          </span>
        )}
      </div>
      {sub && (
        <div className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

export function Spark({
  data,
  w = 120,
  h = 32,
  color,
  fill,
}: {
  data: number[];
  w?: number;
  h?: number;
  color?: string;
  fill?: boolean;
}) {
  if (!data || !data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = w / (data.length - 1);
  const pts: Array<[number, number]> = data.map((v, i) => [
    i * stepX,
    h - 2 - ((v - min) / range) * (h - 4),
  ]);
  const path = (() => {
    if (pts.length < 2) return "";
    let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] ?? pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] ?? pts[i + 1];
      const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
      const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
      const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
      const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    return d;
  })();
  const fillPath = fill ? `${path} L ${w} ${h} L 0 ${h} Z` : "";
  const c = color ?? S.coral;
  const gradId = `spk-${Math.random().toString(36).slice(2, 7)}`;
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity="0.45" />
          <stop offset="100%" stopColor={c} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={fillPath} fill={`url(#${gradId})`} />}
      <path
        d={path}
        fill="none"
        stroke={c}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last[0]} cy={last[1]} r="2.8" fill={c} />
      <circle cx={last[0]} cy={last[1]} r="6" fill={c} opacity="0.18" />
    </svg>
  );
}

export function CorrBar({
  label,
  value,
  threshold = 0.95,
}: {
  label: string;
  value: number;
  threshold?: number;
}) {
  const pct = ((value + 1) / 2) * 100;
  const overThreshold = Math.abs(value) > threshold;
  const c = overThreshold
    ? S.coral
    : Math.abs(value) > 0.7
      ? S.amber
      : Math.abs(value) > 0.4
        ? S.azure
        : S.mint;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "150px 1fr 64px",
        alignItems: "center",
        gap: 18,
        padding: "4px 0",
      }}
    >
      <span style={{ fontSize: 13, color: S.text2, fontWeight: 500 }}>{label}</span>
      <div style={{ position: "relative", height: 22 }}>
        <div
          style={{
            position: "absolute",
            top: 10,
            left: 0,
            right: 0,
            height: 2,
            background: S.border,
            borderRadius: 1,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 7,
            left: "50%",
            width: 1,
            height: 8,
            background: S.text4,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 6,
            left: `${((threshold + 1) / 2) * 100}%`,
            width: 1,
            height: 10,
            background: S.text4,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 6,
            left: `${((-threshold + 1) / 2) * 100}%`,
            width: 1,
            height: 10,
            background: S.text4,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 3,
            left: `${pct}%`,
            transform: "translateX(-50%)",
            width: 16,
            height: 16,
            borderRadius: "50%",
            background: c,
            boxShadow: `0 0 0 4px ${S.bg}, 0 0 18px ${c}80`,
          }}
        />
      </div>
      <span
        className="sp-num"
        style={{ fontSize: 14, textAlign: "right", color: c, fontWeight: 600 }}
      >
        {value > 0 ? "+" : ""}
        {value.toFixed(2)}
      </span>
    </div>
  );
}

export function SentimentBar({
  pos = 3,
  neu = 4,
  neg = 1,
}: {
  pos?: number;
  neu?: number;
  neg?: number;
}) {
  const total = Math.max(pos + neu + neg, 1);
  return (
    <div>
      <div
        style={{
          display: "flex",
          height: 12,
          borderRadius: 6,
          overflow: "hidden",
          background: S.surfaceHi,
        }}
      >
        <div
          style={{
            width: `${(pos / total) * 100}%`,
            background: `linear-gradient(90deg, ${S.mint}, ${S.mint}cc)`,
            transition: "width .4s",
          }}
        />
        <div
          style={{
            width: `${(neu / total) * 100}%`,
            background: S.text4,
            transition: "width .4s",
          }}
        />
        <div
          style={{
            width: `${(neg / total) * 100}%`,
            background: `linear-gradient(90deg, ${S.rose}cc, ${S.rose})`,
            transition: "width .4s",
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 8,
          fontFamily: S.fMono,
          fontSize: 10,
          color: S.text3,
          letterSpacing: 0.4,
        }}
      >
        <span style={{ color: S.mint }}>● POS {pos}</span>
        <span>● NEU {neu}</span>
        <span style={{ color: S.rose }}>● NEG {neg}</span>
      </div>
    </div>
  );
}

export function CiteChip({
  source,
  title,
  when,
  color,
}: {
  source: string;
  title: string;
  when: string;
  color?: string;
}) {
  return (
    <div
      style={{
        padding: "14px 16px",
        background: S.surface,
        border: `1px solid ${S.border}`,
        borderRadius: 12,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          bottom: 0,
          width: 3,
          background: color ?? S.azure,
        }}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <span
          className="sp-mono"
          style={{
            fontSize: 10,
            letterSpacing: 1,
            textTransform: "uppercase",
            color: color ?? S.azure,
            fontWeight: 600,
          }}
        >
          {source}
        </span>
        <span className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
          {when}
        </span>
      </div>
      <div style={{ fontSize: 14, color: S.text, lineHeight: 1.3, fontWeight: 500 }}>
        {title}
      </div>
    </div>
  );
}

export function Fade({
  in: visible = true,
  delay = 0,
  y = 8,
  children,
  style,
}: {
  in?: boolean;
  delay?: number;
  y?: number;
  children?: React.ReactNode;
  style?: CSS;
}) {
  return (
    <div
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : `translateY(${y}px)`,
        transition: `opacity 360ms ${delay}ms cubic-bezier(.2,.7,.3,1), transform 360ms ${delay}ms cubic-bezier(.2,.7,.3,1)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Skel({
  w = "100%",
  h = 12,
  style,
}: {
  w?: number | string;
  h?: number;
  style?: CSS;
}) {
  return (
    <div
      className="sp-shimmer"
      style={{ width: w, height: h, borderRadius: 4, ...style }}
    />
  );
}
