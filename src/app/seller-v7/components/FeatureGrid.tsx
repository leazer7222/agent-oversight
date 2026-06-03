import { motion } from "framer-motion";
import { Layers, Eye, Calculator, HardHat, TrendingUp } from "lucide-react";

export default function FeatureGrid() {
  const features = [
    {
      icon: <Layers className="w-6 h-6" />,
      title: "Enhanced Project Listing",
      description: "Turn your property into a renovation-ready project with fully defined scope and execution paths."
    },
    {
      icon: <Eye className="w-6 h-6" />,
      title: "Future-State Visualization",
      description: "Show buyers the stunning transformation potential with hyper-realistic AI-driven renders."
    },
    {
      icon: <Calculator className="w-6 h-6" />,
      title: "Instant Cost Clarity",
      description: "Eliminate buyer uncertainty with upfront, accurate renovation cost estimates for the proposed project."
    },
    {
      icon: <HardHat className="w-6 h-6" />,
      title: "Contractor Integration",
      description: "Attach execution directly to the listing. Buyers see which verified pros are ready to build the vision."
    },
    {
      icon: <TrendingUp className="w-6 h-6" />,
      title: "Market Positioning",
      description: "Position your property in the premium tier by selling the outcome, not just the current condition."
    }
  ];

  return (
    <section className="py-24 bg-[#0A192F]">
      <div className="container mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-4xl lg:text-5xl font-bold text-[#CCD6F6] mb-6">
            Everything you need to <span className="text-[#64FFDA]">sell the future.</span>
          </h2>
          <p className="text-lg text-[#8892B0]">
            ReformAI bridges the imagination gap, giving buyers the certainty they need to pay a premium for your property's potential.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="p-10 bg-[#112240] rounded-3xl border border-white/10 hover:border-[#00ADB5]/50 hover:bg-[#112240]/80 transition-all group relative overflow-hidden"
            >
              <div className="w-14 h-14 bg-[#00ADB5]/10 rounded-xl flex items-center justify-center text-[#64FFDA] mb-8 group-hover:bg-[#00ADB5] group-hover:text-[#0A192F] transition-all duration-300">
                {feature.icon}
              </div>
              <h3 className="text-2xl font-bold text-[#CCD6F6] mb-4">{feature.title}</h3>
              <p className="text-[#8892B0] leading-relaxed">
                {feature.description}
              </p>
              <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-[#00ADB5]/5 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity" />
            </motion.div>
          ))}
          
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.5 }}
            className="p-10 bg-gradient-to-br from-[#112240] to-[#00ADB5]/10 rounded-3xl border border-[#00ADB5]/30 relative overflow-hidden lg:col-span-1"
          >
            <h3 className="text-2xl font-bold text-[#64FFDA] mb-6">Why ReformAI Wins</h3>
            <ul className="space-y-4">
              {[
                "Decision-ready assets for buyers",
                "Reduced time on market",
                "Increased buyer confidence",
                "Maximize value without blind renovation"
              ].map((item, i) => (
                <li key={i} className="flex items-start gap-3 text-[#CCD6F6]">
                  <div className="w-1.5 h-1.5 bg-[#64FFDA] rounded-full mt-2.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
