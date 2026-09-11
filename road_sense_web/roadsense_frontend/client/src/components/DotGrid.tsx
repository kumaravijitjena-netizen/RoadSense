import { useEffect, useRef } from "react";

type DotGridProps = {
  className?: string;
  dotSize?: number;
  gap?: number;
  baseColor?: string;
  activeColor?: string;
  proximity?: number;
};

function hexToRgb(hex: string) {
  const value = hex.replace("#", "");
  return { r: Number.parseInt(value.slice(0, 2), 16), g: Number.parseInt(value.slice(2, 4), 16), b: Number.parseInt(value.slice(4, 6), 16) };
}

export function DotGrid({ className, dotSize = 2, gap = 24, baseColor = "#c6d7d1", activeColor = "#f0c56a", proximity = 140 }: DotGridProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef({ x: -9999, y: -9999 });
  const drawRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const base = hexToRgb(baseColor), active = hexToRgb(activeColor);
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      const width = Math.round(rect.width * ratio), height = Math.round(rect.height * ratio);
      if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0); context.clearRect(0, 0, rect.width, rect.height);
      for (let y = gap / 2; y < rect.height; y += gap) {
        for (let x = gap / 2; x < rect.width; x += gap) {
          const distance = Math.hypot(pointerRef.current.x - x, pointerRef.current.y - y);
          const intensity = Math.max(0, 1 - distance / proximity);
          const r = Math.round(base.r + (active.r - base.r) * intensity);
          const g = Math.round(base.g + (active.g - base.g) * intensity);
          const b = Math.round(base.b + (active.b - base.b) * intensity);
          context.fillStyle = `rgb(${r}, ${g}, ${b})`;
          context.globalAlpha = .18 + intensity * .7;
          context.beginPath(); context.arc(x, y, dotSize / 2 + intensity * 1.4, 0, Math.PI * 2); context.fill();
        }
      }
      context.globalAlpha = 1;
    };
    drawRef.current = draw;
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => { observer.disconnect(); drawRef.current = null; };
  }, [activeColor, baseColor, dotSize, gap, proximity]);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" onPointerMove={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); pointerRef.current = { x: event.clientX - bounds.left, y: event.clientY - bounds.top }; drawRef.current?.(); }} onPointerLeave={() => { pointerRef.current = { x: -9999, y: -9999 }; drawRef.current?.(); }} />;
}
