export default function Footer() {
  return (
    <footer className="py-20 bg-[#06101F] border-t border-white/5">
      <div className="container mx-auto px-6 grid grid-cols-1 md:grid-cols-4 gap-12">
        <div className="col-span-1 md:col-span-2">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-8 h-8 bg-[#00ADB5] rounded flex items-center justify-center font-bold text-[#0A192F]">R</div>
            <span className="text-xl font-bold text-white">Reform-A.i</span>
          </div>
          <p className="text-[#8892B0] max-w-sm mb-6 leading-relaxed">
            Leading the PropTech revolution by turning property listings into fully defined, ready-to-execute renovation projects.
          </p>
        </div>
        
        <div>
          <h4 className="text-[#CCD6F6] font-bold mb-6">Solutions</h4>
          <ul className="space-y-4 text-[#8892B0]">
            <li><a href="#" className="hover:text-[#64FFDA]">For Buyers</a></li>
            <li><a href="#" className="hover:text-[#64FFDA]">For Sellers</a></li>
            <li><a href="#" className="hover:text-[#64FFDA]">For Contractors</a></li>
          </ul>
        </div>

        <div>
          <h4 className="text-[#CCD6F6] font-bold mb-6">Company</h4>
          <ul className="space-y-4 text-[#8892B0]">
            <li><a href="#" className="hover:text-[#64FFDA]">About</a></li>
            <li><a href="#" className="hover:text-[#64FFDA]">Careers</a></li>
          </ul>
        </div>
      </div>
      
      <div className="container mx-auto px-6 mt-20 pt-8 border-t border-white/5 text-center text-[#8892B0] text-sm">
        © 2026 Reform AI. All rights reserved.
      </div>
    </footer>
  );
}
