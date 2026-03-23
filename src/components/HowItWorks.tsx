"use client";

import { motion } from "framer-motion";

const steps = [
  { number: "01", title: "Find a Property", description: "Browse listings or upload photos of a property you're evaluating. Our AI instantly analyzes renovation potential." },
  { number: "02", title: "Visualize the Renovation", description: "Upload room photos and get AI-generated before/after visualizations. Explore different styles in seconds." },
  { number: "03", title: "Get Your Estimate", description: "Receive AI-calculated renovation cost breakdowns and After Repair Value estimates for your local market." },
  { number: "04", title: "Execute with Confidence", description: "Connect with vetted pros, track your budget, and manage the whole project from one dashboard." },
];

export default function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="w-full py-24 px-6"
      style={{ background: "linear-gradient(180deg, #0a1628 0%, #060f1e 100%)" }}
    >
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <motion.span
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-[13px] font-semibold uppercase tracking-widest"
            style={{ fontFamily: "'Red Hat Display', sans-serif", color: "#00ADB5" }}
          >
            How It Works
          </motion.span>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="mt-3 font-semibold"
            style={{
              fontFamily: "'Red Hat Display', sans-serif",
              fontSize: "clamp(26px, 3.5vw, 36px)",
              background: "linear-gradient(180deg, #ffffff 0%, rgba(255,255,255,0.7) 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            From property to profit in 4 steps
          </motion.h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {steps.map((step, i) => (
            <motion.div
              key={step.number}
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.6, delay: i * 0.12 }}
              className="flex flex-col gap-5 relative"
            >
              {/* Connector line */}
              {i < steps.length - 1 && (
                <motion.div
                  initial={{ scaleX: 0 }}
                  whileInView={{ scaleX: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.8, delay: i * 0.12 + 0.4 }}
                  className="hidden lg:block absolute top-5 left-[52px] right-[-32px] h-px origin-left"
                  style={{ background: "linear-gradient(90deg, rgba(0,173,181,0.4), rgba(0,173,181,0.05))" }}
                />
              )}

              {/* Step number */}
              <motion.div
                whileHover={{ scale: 1.1, boxShadow: "0 0 24px rgba(0,173,181,0.5)" }}
                className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-[13px] relative z-10"
                style={{
                  fontFamily: "'Red Hat Display', sans-serif",
                  background: "linear-gradient(135deg, #00ADB5, #3B8AA2)",
                  color: "white",
                  boxShadow: "0 0 16px rgba(0,173,181,0.3)",
                }}
              >
                {step.number}
              </motion.div>

              {/* Content */}
              <div
                className="p-5 rounded-2xl"
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  backdropFilter: "blur(8px)",
                }}
              >
                <h3
                  className="text-white font-semibold text-[15px] mb-2"
                  style={{ fontFamily: "'Red Hat Display', sans-serif" }}
                >
                  {step.title}
                </h3>
                <p
                  className="text-[13px] leading-5"
                  style={{ fontFamily: "'Red Hat Display', sans-serif", color: "rgba(255,255,255,0.45)" }}
                >
                  {step.description}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
