import { motion } from "framer-motion";
import { ArrowRight, BarChart3 } from "lucide-react";

export default function FinalCTA() {
  return (
    <section className="py-32 bg-[#0A192F] relative overflow-hidden">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-[#00ADB5]/5 blur-[150px] rounded-full" />

      <div className="container mx-auto px-6 relative z-10 text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          className="max-w-4xl mx-auto p-12 lg:p-20 bg-white/5 backdrop-blur-xl rounded-[40px] border border-white/10 shadow-2xl overflow-hidden relative"
        >
          <div className="absolute top-0 right-0 p-10 opacity-10">
            <BarChart3 className="w-40 h-40 text-[#64FFDA]" />
          </div>

          <h2 className="text-4xl lg:text-6xl font-bold text-[#CCD6F6] mb-8 tracking-tight">
            Ready to unlock your <br />
            <span className="text-[#00ADB5]">property's true potential?</span>
          </h2>
          <p className="text-xl text-[#8892B0] mb-12 max-w-2xl mx-auto">
            Get an instant AI analysis and show buyers the outcome they’ve been searching for. Maximize your sale price without the risk of blind renovation.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-6 justify-center">
            <button className="px-10 py-5 bg-[#00ADB5] hover:bg-[#64FFDA] hover:text-[#0A192F] text-[#0A192F] font-bold text-lg rounded-xl transition-all flex items-center justify-center gap-3 group shadow-lg shadow-[#00ADB5]/20 hover:shadow-[#64FFDA]/40">
              Analyze My Property
              <ArrowRight className="w-6 h-6 group-hover:translate-x-2 transition-transform" />
            </button>
            <button className="px-10 py-5 bg-[#112240] hover:bg-[#112240]/80 text-[#CCD6F6] font-bold text-lg rounded-xl border border-white/10 transition-all">
              Talk to a Strategist
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
