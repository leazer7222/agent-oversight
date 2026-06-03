"use client";

import { motion } from "framer-motion";

export default function CTA() {
  return (
    <section className="w-full py-24 px-6" style={{ background: "#060f1e" }}>
      <div className="max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
          className="relative rounded-3xl overflow-hidden flex flex-col items-center text-center gap-7 px-8 py-20"
          style={{ background: "linear-gradient(135deg, #060f1e 0%, #0d2d40 50%, #0f3d45 100%)" }}
        >
          {/* Grid overlay */}
          <div
            className="absolute inset-0 opacity-[0.05]"
            style={{
              backgroundImage: "linear-gradient(rgba(0,173,181,1) 1px, transparent 1px), linear-gradient(90deg, rgba(0,173,181,1) 1px, transparent 1px)",
              backgroundSize: "50px 50px",
            }}
          />

          {/* Glow orbs */}
          <div className="absolute top-[-60px] left-[-60px] w-64 h-64 rounded-full pointer-events-none"
            style={{ background: "radial-gradient(circle, rgba(0,173,181,0.15), transparent 70%)" }} />
          <div className="absolute bottom-[-60px] right-[-60px] w-64 h-64 rounded-full pointer-events-none"
            style={{ background: "radial-gradient(circle, rgba(59,138,162,0.15), transparent 70%)" }} />

          {/* Border glow */}
          <div className="absolute inset-0 rounded-3xl pointer-events-none"
            style={{ border: "1px solid rgba(0,173,181,0.2)", boxShadow: "inset 0 0 60px rgba(0,173,181,0.04)" }} />

          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="relative z-10 font-bold"
            style={{
              fontFamily: "'Red Hat Display', sans-serif",
              fontSize: "clamp(30px, 4.5vw, 48px)",
              lineHeight: "1.15",
              background: "linear-gradient(180deg, #ffffff 0%, rgba(255,255,255,0.75) 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Ready to maximize your home's value?
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="relative z-10 max-w-md"
            style={{
              fontFamily: "'Red Hat Display', sans-serif",
              fontSize: "16px",
              lineHeight: "26px",
              color: "rgba(255,255,255,0.5)",
            }}
          >
            Join homeowners using AI to visualize high-impact renovations, estimate ROI, and sell for a premium. Start your high-value sale journey today.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="relative z-10 flex flex-wrap gap-3 justify-center"
          >
            <motion.a
              href="#"
              whileHover={{ scale: 1.05, boxShadow: "0 0 32px rgba(0,173,181,0.5)" }}
              whileTap={{ scale: 0.97 }}
              className="px-8 py-3.5 rounded-xl font-semibold text-[15px] text-white bg-[#00ADB5]"
              style={{ fontFamily: "'Red Hat Display', sans-serif" }}
            >
              Get Started Free
            </motion.a>
            <motion.a
              href="#"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.97 }}
              className="px-8 py-3.5 rounded-xl font-medium text-[15px] text-white"
              style={{
                fontFamily: "'Red Hat Display', sans-serif",
                background: "rgba(255,255,255,0.07)",
                border: "1px solid rgba(255,255,255,0.14)",
                backdropFilter: "blur(8px)",
              }}
            >
              Book a Demo
            </motion.a>
          </motion.div>

          <p
            className="relative z-10 text-[12px]"
            style={{ fontFamily: "'Red Hat Display', sans-serif", color: "rgba(255,255,255,0.25)" }}
          >
            No credit card required · Free plan available
          </p>
        </motion.div>
      </div>
    </section>
  );
}
