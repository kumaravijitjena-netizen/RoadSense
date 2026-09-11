import { useEffect, useRef, useState } from "react";

type DecryptedTextProps = {
  text: string;
  className?: string;
  speed?: number;
  revealDirection?: "start" | "center" | "end";
  startDelay?: number;
};

const characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*";

function scrambledText(text: string, revealed: Set<number>) {
  return Array.from(text, (character, index) => {
    if (character === " " || revealed.has(index)) return character;
    return characters[Math.floor(Math.random() * characters.length)];
  }).join("");
}

function revealOrder(length: number, direction: DecryptedTextProps["revealDirection"]) {
  if (direction === "start") return Array.from({ length }, (_, index) => index);
  if (direction === "end") return Array.from({ length }, (_, index) => length - index - 1);
  const order: number[] = [];
  const center = Math.floor((length - 1) / 2);
  for (let offset = 0; order.length < length; offset += 1) {
    const left = center - offset;
    const right = center + offset + (length % 2 === 0 ? 1 : 0);
    if (left >= 0) order.push(left);
    if (right < length && right !== left) order.push(right);
  }
  return order;
}

export function DecryptedText({ text, className, speed = 42, revealDirection = "start", startDelay = 0 }: DecryptedTextProps) {
  const elementRef = useRef<HTMLSpanElement>(null);
  const [displayText, setDisplayText] = useState(text);

  useEffect(() => {
    const element = elementRef.current;
    if (!element || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let started = false;
    let timer: number | undefined;
    let delayTimer: number | undefined;
    const start = () => {
      if (started) return;
      started = true;
      const order = revealOrder(text.length, revealDirection);
      const revealed = new Set<number>();
      let step = 0;
      setDisplayText(scrambledText(text, revealed));
      timer = window.setInterval(() => {
        revealed.add(order[step]);
        step += 1;
        setDisplayText(step >= order.length ? text : scrambledText(text, revealed));
        if (step >= order.length && timer !== undefined) window.clearInterval(timer);
      }, speed);
    };
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) delayTimer = window.setTimeout(start, startDelay);
    }, { threshold: 0.6 });
    observer.observe(element);
    return () => { observer.disconnect(); if (timer !== undefined) window.clearInterval(timer); if (delayTimer !== undefined) window.clearTimeout(delayTimer); };
  }, [revealDirection, speed, startDelay, text]);

  return <span ref={elementRef} className={className} aria-label={text}>{displayText}</span>;
}
