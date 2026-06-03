import { motion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";

export default function HeroSection() {
  return (
    <section className="relative min-h-[90vh] flex items-center justify-center pt-24 overflow-hidden bg-[#0A192F]">
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
        <div className="absolute top-[10%] left-[5%] w-[40rem] h-[40rem] bg-[#00ADB5]/10 rounded-full blur-[120px]" />
        <div className="absolute bottom-[10%] right-[5%] w-[35rem] h-[35rem] bg-[#64FFDA]/5 rounded-full blur-[100px]" />
      </div>

      <div className="container mx-auto px-6 relative z-10 flex flex-col lg:flex-row items-center gap-16">
        <div className="flex-1 text-center lg:text-left">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#112240] border border-white/10 text-[#64FFDA] text-sm font-medium mb-6"
          >
            <Sparkles className="w-4 h-4" />
            <span>Maximize Your Property Value</span>
          </motion.div>

          <h1 className="text-5xl lg:text-7xl font-bold text-[#CCD6F6] leading-[1.1] tracking-tight mb-8">
            Don’t sell what your property is. <br />
            <span className="text-[#00ADB5]">Sell what it can become.</span>
          </h1>

          <p className="text-xl text-[#8892B0] max-w-2xl mb-10 leading-relaxed">
            Show buyers the transformation, cost, and execution path — before they decide. 
            Turn your outdated property into a high-value, ready-to-execute project.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
            <button className="px-8 py-4 bg-[#00ADB5] hover:bg-[#00ADB5]/90 text-[#0A192F] font-bold rounded-lg transition-all flex items-center justify-center gap-2 group shadow-[0_0_20px_rgba(0,173,181,0.3)]">
              Analyze My Property
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
            <button className="px-8 py-4 bg-transparent border border-[#00ADB5]/30 hover:border-[#00ADB5] text-[#CCD6F6] font-semibold rounded-lg transition-all">
              See Case Studies
            </button>
          </div>
        </div>

        <div className="flex-1 relative w-full aspect-[4/3] max-w-[600px]">
          <div className="absolute inset-0 bg-[#112240] rounded-2xl border border-white/10 overflow-hidden shadow-2xl">
            <div className="absolute inset-0 bg-gradient-to-tr from-[#0A192F]/80 to-transparent z-10" />
            <img 
              src="/hero-render.png" 
              alt="Transformed Property Outcome" 
              className="w-full h-full object-cover opacity-60 mix-blend-overlay scale-110"
            />
            
            <div className="absolute bottom-8 left-8 right-8 p-6 bg-white/5 backdrop-blur-md rounded-xl border border-white/10 z-20">
              <div className="flex justify-between items-center text-white">
                <div>
                  <p className="text-[#8892B0] text-sm mb-1 uppercase tracking-wider font-semibold">Future Market Value</p>
                  <p className="text-3xl font-bold text-[#64FFDA]">$1,250,000</p>
                </div>
                <div className="text-right">
                  <p className="text-[#8892B0] text-sm mb-1 uppercase tracking-wider font-semibold">Projected ROI</p>
                  <p className="text-2xl font-bold">+28%</p>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute -inset-4 bg-[#00ADB5]/20 blur-[40px] rounded-[100px] -z-10" />
        </div>
      </div>
    </section>
  );
}
