export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 py-6 px-6 backdrop-blur-md bg-[#0A192F]/60 border-b border-white/5">
      <div className="container mx-auto flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 bg-gradient-to-br from-[#00ADB5] to-[#64FFDA] rounded-lg rotate-12 flex items-center justify-center font-black text-[#0A192F] text-xl">
            R
          </div>
          <span className="text-2xl font-bold tracking-tight text-white">Reform-A.i</span>
        </div>
        
        <div className="hidden md:flex items-center gap-8 text-[#8892B0] font-medium">
          <a href="#" className="hover:text-[#64FFDA] transition-colors">How it works</a>
          <a href="#" className="hover:text-[#64FFDA] transition-colors">Case Studies</a>
          <a href="#" className="hover:text-[#64FFDA] transition-colors">Pricing</a>
          <button className="px-5 py-2.5 bg-[#00ADB5] text-[#0A192F] font-bold rounded-lg hover:bg-[#64FFDA] transition-all">
            Get Started
          </button>
        </div>
      </div>
    </nav>
  );
}
