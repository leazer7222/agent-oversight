import { Red_Hat_Display } from "next/font/google";
import "./seller.css";

const redHatDisplay = Red_Hat_Display({
  subsets: ["latin"],
  variable: "--font-red-hat-display",
});

export default function SellerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={`${redHatDisplay.variable} font-sans bg-[#0A192F] text-[#CCD6F6]`}>
      {children}
    </div>
  );
}
