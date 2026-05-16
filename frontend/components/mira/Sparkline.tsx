"use client";

interface Props {
  data: number[];
  width?: number;
  height?: number;
  accent?: boolean;
}

export default function Sparkline({ data, width = 320, height = 80, accent = false }: Props) {
  if (!data || data.length < 2) {
    return <svg width={width} height={height} />;
  }
  const padY = 6;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data.map((v, i) => [i * stepX, height - padY - ((v - min) / span) * (height - padY * 2)] as const);
  const path = points.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  const last = points[points.length - 1];
  const up = data[data.length - 1] >= data[0];
  const stroke = accent ? "var(--primary)" : up ? "var(--pos)" : "var(--neg)";
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: "block" }}
    >
      <path d={area} fill={stroke} opacity="0.08" />
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="3" fill={stroke} />
    </svg>
  );
}
