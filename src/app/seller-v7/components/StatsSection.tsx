import { motion } from "framer-motion";

export default function StatsSection() {
  const stats = [
    { label: "Increase in Perceived Value", value: "24%", detail: "Avg. increase in listing interest" },
    { label: "Reduced Time on Market", value: "-45%", detail: "Faster close with projected outcome" },
    { label: "Project ROI", value: "3.2x", detail: "Return on renovation investment" },
    { label: "Buyer Confidence", value: "High", detail: "Eliminates decision friction" },
  ];

  return (
    <section className="py-24 bg-[#0A192F] border-y border-white/5">
      <div className="container mx-auto px-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {stats.map((stat, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="p-8 bg-[#112240]/40 backdrop-blur-sm rounded-2xl border border-white/5 hover:border-[#00ADB5]/30 transition-all text-center group"
            >
              <h3 className="text-4xl font-bold text-[#64FFDA] mb-2 group-hover:scale-110 transition-transform duration-300">
                {stat.value}
              </h3>
              <p className="text-[#CCD6F6] font-semibold mb-1">{stat.label}</p>
              <p className="text-[#8892B0] text-sm">{stat.detail}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
