"use client";

import { motion } from "framer-motion";

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.9, delay: 0.3 + i * 0.15, ease: [0.25, 0.4, 0.25, 1] },
  }),
};

export default function Hero() {
  return (
    <section
      className="relative w-full flex items-center overflow-hidden px-6"
      style={{
        background: "linear-gradient(135deg, #050e1d 0%, #0a1323 50%, #0d2035 100%)",
        minHeight: "680px",
        paddingTop: "80px",
        paddingBottom: "80px",
      }}
    >
      {/* Animated grid */}
      <div className="absolute inset-0 opacity-[0.04]" style={{
        backgroundImage: "linear-gradient(rgba(85,216,225,1) 1px, transparent 1px), linear-gradient(90deg, rgba(85,216,225,1) 1px, transparent 1px)",
        backgroundSize: "60px 60px",
      }} />

      {/* Hexagonal glow blobs */}
      <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-16 right-[8%] w-72 h-72 rounded-full opacity-10 blur-3xl" style={{ background: "#00ADB5" }} />
        <div className="absolute bottom-16 left-[4%] w-96 h-96 rounded-full opacity-5 blur-3xl" style={{ background: "#00ADB5" }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full border opacity-10" style={{ borderColor: "rgba(0,173,181,0.3)" }} />
        {/* Floating hexagons */}
        {[
          { top: "10%", right: "18%", size: 90, delay: 0.2, opacity: 0.12 },
          { top: "65%", right: "5%",  size: 140, delay: 0.4, opacity: 0.08 },
          { top: "20%", left: "2%",   size: 180, delay: 0.3, opacity: 0.07 },
          { top: "70%", left: "15%",  size: 70,  delay: 0.6, opacity: 0.11 },
          { top: "5%",  left: "30%",  size: 50,  delay: 0.7, opacity: 0.08 },
        ].map((h, i) => (
          <motion.div
            key={i}
            className="absolute"
            style={{ top: h.top, left: h.left, right: (h as any).right }}
            animate={{ y: [0, 16, 0], rotate: [0, 4, 0] }}
            transition={{ duration: 12 + i * 2, repeat: Infinity, ease: "easeInOut", delay: h.delay }}
          >
            <svg width={h.size} height={h.size} viewBox="0 0 100 100" fill="none">
              <path d="M50 5L93.3 27.5V72.5L50 95L6.7 72.5V27.5L50 5Z"
                fill="#00ADB5" fillOpacity={h.opacity}
                stroke="#00ADB5" strokeOpacity={h.opacity * 2} strokeWidth="1.5" />
            </svg>
          </motion.div>
        ))}
      </div>

      {/* Two-column layout */}
      <div className="relative z-10 max-w-6xl mx-auto w-full grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">

        {/* Left: Copy */}
        <div className="flex flex-col gap-7">
          <motion.span
            custom={0} variants={fadeUp} initial="hidden" animate="visible"
            className="inline-flex items-center gap-2 self-start px-4 py-1.5 rounded-full text-[12px] font-semibold tracking-widest uppercase"
            style={{ background: "rgba(0,173,181,0.1)", color: "#55d8e1", border: "1px solid rgba(0,173,181,0.25)" }}
          >
            <motion.span animate={{ scale: [1, 1.5, 1], opacity: [1, 0.5, 1] }} transition={{ duration: 2, repeat: Infinity }}
              className="w-1.5 h-1.5 rounded-full inline-block bg-[#00ADB5]" />
            AI-Powered Renovation
          </motion.span>

          <motion.h1
            custom={1} variants={fadeUp} initial="hidden" animate="visible"
            className="font-bold text-white"
            style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: "clamp(38px, 5vw, 64px)", lineHeight: 1.08, letterSpacing: "-0.02em" }}
          >
            Sell Your Home for More,{" "}
            <span style={{ background: "linear-gradient(90deg, #55d8e1, #00ADB5)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Renovate with AI
            </span>
          </motion.h1>

          <motion.p
            custom={2} variants={fadeUp} initial="hidden" animate="visible"
            style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: "18px", lineHeight: "28px", color: "rgba(217,227,248,0.6)", maxWidth: "480px" }}
          >
            Visualize the perfect renovation, estimate exact ROI, and sell for a premium. No more guesswork — just data-driven results for homeowners ready for a high-value sale.
          </motion.p>

          <motion.div custom={3} variants={fadeUp} initial="hidden" animate="visible" className="flex flex-wrap gap-3">
            <motion.a
              href="#"
              whileHover={{ scale: 1.04, boxShadow: "0 0 32px rgba(0,173,181,0.5)" }}
              whileTap={{ scale: 0.97 }}
              className="px-8 py-4 rounded-lg font-bold text-[15px] text-white"
              style={{ fontFamily: "'Red Hat Display', sans-serif", background: "linear-gradient(135deg, #55d8e1, #00ADB5)" }}
            >
              Start for Free
            </motion.a>
            <motion.a
              href="#how-it-works"
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              className="px-8 py-4 rounded-lg font-bold text-[15px] text-white"
              style={{
                fontFamily: "'Red Hat Display', sans-serif",
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.12)",
                backdropFilter: "blur(12px)",
              }}
            >
              See How It Works
            </motion.a>
          </motion.div>

          <motion.div custom={4} variants={fadeUp} initial="hidden" animate="visible" className="flex items-center gap-3">
            <div className="flex -space-x-2">
              {["#00ADB5","#55d8e1","#3B8AA2","#104e64","#0a1628"].map((bg, i) => (
                <div key={i} className="w-7 h-7 rounded-full border-2" style={{ backgroundColor: bg, borderColor: "#050e1d" }} />
              ))}
            </div>
            <p style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: "13px", color: "rgba(217,227,248,0.4)" }}>
              Trusted by <span style={{ color: "rgba(217,227,248,0.75)" }}>500+</span> property investors
            </p>
          </motion.div>
        </div>

        {/* Right: AI-generated room preview */}
        <motion.div
          custom={2} variants={fadeUp} initial="hidden" animate="visible"
          className="hidden lg:block relative"
        >
          <div className="relative rounded-2xl overflow-hidden" style={{ border: "1px solid rgba(0,173,181,0.15)", boxShadow: "0 0 60px rgba(0,173,181,0.08)" }}>
            {/* Glassmorphism overlay */}
            <div className="absolute inset-0 z-10" style={{ background: "linear-gradient(to top, #050e1d 0%, transparent 50%)" }} />
            <img
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuBbgwWkBWd_Okwp4HJBeA8rA3iQmBFdHYVLVMK3CSZlAWZPMCMvJjrAVRhVFruIS8hjYQv0U-wqwRQe1zb-qQqup8rTeWayLOAZwiTJu0P1h4peFXomWhwNb5o0kgrj4dS8Okwsemh_HhURaDtQ3T9MukhlY3IbEapfBMvg2rXPZ_lIZnomvebj2ugv54d75ydOgJecTuYsGan8FILmDTiTpVYO320Gg-uWtl8Jx0MbIyX6yztQiFKcSm8jocxINul079w5ddr6xiFC"
              alt="AI-generated architectural renovation"
              className="w-full object-cover"
              style={{ aspectRatio: "4/5", filter: "grayscale(20%) brightness(0.85)" }}
            />
            {/* Bottom label */}
            <div className="absolute bottom-0 left-0 right-0 z-20 p-6">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-[#00ADB5] animate-pulse" />
                <span className="text-[11px] font-bold tracking-widest uppercase" style={{ fontFamily: "'Red Hat Display', sans-serif", color: "#55d8e1" }}>
                  A.I. Generated Visualization
                </span>
              </div>
              <div className="w-full rounded-full overflow-hidden" style={{ height: "3px", background: "rgba(255,255,255,0.1)" }}>
                <motion.div
                  className="h-full rounded-full bg-[#00ADB5]"
                  initial={{ width: "0%" }}
                  animate={{ width: "67%" }}
                  transition={{ duration: 2, delay: 1.5, ease: "easeOut" }}
                />
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
