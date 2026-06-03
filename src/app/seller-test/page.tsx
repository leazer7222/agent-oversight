"use client";

import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import Stats from "./components/Stats";
import Features from "./components/Features";
import HowItWorks from "./components/HowItWorks";
import CTA from "./components/CTA";
import Footer from "./components/Footer";

export default function HomeownerSellerPage() {
  return (
    <main className="min-h-screen bg-[#050e1d] text-white selection:bg-[#00ADB5]/30">
      <Navbar />
      <Hero />
      <div className="relative z-10 -mt-12">
        <Stats />
      </div>
      <Features />
      <HowItWorks />
      <CTA />
      <Footer />
    </main>
  );
}
