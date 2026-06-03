"use client";

import { motion } from "framer-motion";

export default function Navbar() {
  return (
    <motion.header
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.25, 0.4, 0.25, 1] }}
      className="sticky top-0 z-50 w-full"
      style={{
        background: "rgba(6,15,30,0.8)",
        backdropFilter: "blur(16px)",
        borderBottom: "1px solid rgba(255,255,255,0.07)",
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <svg width="26" height="26" viewBox="0 0 28 28" fill="none">
            <path d="M14 2L25.258 8.5V21.5L14 28L2.742 21.5V8.5L14 2Z" fill="#00ADB5" />
            <path d="M10 19L14 9L18 19M11.5 16H16.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-white font-bold text-[17px] tracking-tight" style={{ fontFamily: "'Red Hat Display', sans-serif" }}>
            Reform-A.i
          </span>
        </div>

        {/* Nav links */}
        <nav className="hidden md:flex items-center gap-7">
          {["Features", "How It Works", "Pricing"].map((link) => (
            <a
              key={link}
              href={`#${link.toLowerCase().replace(/\s+/g, "-")}`}
              className="text-[14px] font-medium transition-colors text-white/50 hover:text-white/90"
              style={{ fontFamily: "'Red Hat Display', sans-serif" }}
            >
              {link}
            </a>
          ))}
        </nav>

        {/* CTAs */}
        <div className="flex items-center gap-3">
          <a
            href="#"
            className="hidden md:inline text-[14px] font-medium transition-colors text-white/50 hover:text-white/90"
            style={{ fontFamily: "'Red Hat Display', sans-serif" }}
          >
            Sign in
          </a>
          <motion.a
            href="#"
            whileHover={{ scale: 1.04, boxShadow: "0 0 20px rgba(0,173,181,0.4)" }}
            whileTap={{ scale: 0.97 }}
            className="text-[14px] font-semibold text-white px-4 py-2 rounded-lg bg-[#00ADB5]"
            style={{ fontFamily: "'Red Hat Display', sans-serif" }}
          >
            Get Started
          </motion.a>
        </div>
      </div>
    </motion.header>
  );
}
