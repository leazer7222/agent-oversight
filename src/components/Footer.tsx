const links = {
  Product: ["Features", "How It Works", "Pricing", "Changelog"],
  Company: ["About", "Blog", "Careers", "Press"],
  Legal: ["Privacy Policy", "Terms of Service", "Cookie Policy"],
};

export default function Footer() {
  return (
    <footer
      className="w-full px-6 py-12"
      style={{ background: "#060f1e", borderTop: "1px solid rgba(255,255,255,0.06)" }}
    >
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1 flex flex-col gap-4">
            <div className="flex items-center gap-2">
              <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
                <path d="M14 2L25.258 8.5V21.5L14 28L2.742 21.5V8.5L14 2Z" fill="#00ADB5" />
                <path d="M10 19L14 9L18 19M11.5 16H16.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="font-bold text-white text-[15px]" style={{ fontFamily: "'Red Hat Display', sans-serif" }}>
                Reform-A.i
              </span>
            </div>
            <p className="text-[13px] leading-5 text-white/35" style={{ fontFamily: "'Red Hat Display', sans-serif" }}>
              Renovation Made Easy. AI-powered tools for smart property investors.
            </p>
          </div>

          {Object.entries(links).map(([category, items]) => (
            <div key={category}>
              <p
                className="text-[11px] font-semibold uppercase tracking-widest mb-3 text-white/30"
                style={{ fontFamily: "'Red Hat Display', sans-serif" }}
              >
                {category}
              </p>
              <ul className="flex flex-col gap-2">
                {items.map((item) => (
                  <li key={item}>
                    <a
                      href="#"
                      className="text-[14px] text-white/40 hover:text-white/80 transition-colors"
                      style={{ fontFamily: "'Red Hat Display', sans-serif" }}
                    >
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div
          className="pt-6 flex flex-col sm:flex-row items-center justify-between gap-2"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
        >
          <p className="text-[12px] text-white/25" style={{ fontFamily: "'Red Hat Display', sans-serif" }}>
            © {new Date().getFullYear()} Reform-A.i. All rights reserved.
          </p>
          <p className="text-[12px] text-white/25" style={{ fontFamily: "'Red Hat Display', sans-serif" }}>
            Renovation Made Easy
          </p>
        </div>
      </div>
    </footer>
  );
}
