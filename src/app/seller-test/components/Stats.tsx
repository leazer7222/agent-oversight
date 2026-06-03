"use client";

import { motion, useInView, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";

const stats = [
  { value: 500, suffix: "+", label: "Property Investors" },
  { value: 10000, suffix: "+", label: "AI Visualizations" },
  { value: 98, suffix: "%", label: "Satisfaction Rate" },
  { value: 3, suffix: "x", label: "Average ROI Boost" },
];

function AnimatedNumber({ value, suffix }: { value: number; suffix: string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const motionVal = useMotionValue(0);
  const spring = useSpring(motionVal, { damping: 40, stiffness: 120 });
  const rounded = useTransform(spring, (latest: number) => Math.round(latest).toLocaleString());

  useEffect(() => {
    if (inView) motionVal.set(value);
  }, [inView, motionVal, value]);

  return (
    <span ref={ref} className="tabular-nums">
      <motion.span>{rounded}</motion.span>
      {suffix}
    </span>
  );
}

export default function Stats() {
  return (
    <section
      className="w-full py-16 px-6"
      style={{ background: "#060f1e", borderTop: "1px solid rgba(0,173,181,0.1)", borderBottom: "1px solid rgba(0,173,181,0.1)" }}
    >
      <div className="max-w-5xl mx-auto grid grid-cols-2 lg:grid-cols-4 gap-8">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: i * 0.1 }}
            className="flex flex-col items-center text-center gap-1"
          >
            <span
              className="font-bold"
              style={{
                fontFamily: "'Red Hat Display', sans-serif",
                fontSize: "clamp(32px, 4vw, 44px)",
                background: "linear-gradient(90deg, #00ADB5, #A5D0FA)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              <AnimatedNumber value={stat.value} suffix={stat.suffix} />
            </span>
            <span
              className="text-[13px]"
              style={{ fontFamily: "'Red Hat Display', sans-serif", color: "rgba(255,255,255,0.4)" }}
            >
              {stat.label}
            </span>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
