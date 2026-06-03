"use client";

import HeroSection from "./components/HeroSection";
import StatsSection from "./components/StatsSection";
import FeatureGrid from "./components/FeatureGrid";
import FinalCTA from "./components/FinalCTA";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";

export default function SellerLandingPage() {
  return (
    <main className="min-h-screen bg-[#0A192F] font-sans selection:bg-[#00ADB5] selection:text-[#0A192F]">
      <Navbar />
      <HeroSection />
      <StatsSection />
      <FeatureGrid />
      <FinalCTA />
      <Footer />
    </main>
  );
}
