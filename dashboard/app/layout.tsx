import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME ?? "LedgerFlow",
  description: "Real-time banking analytics dashboard — PaySim fraud intelligence",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "LedgerFlow";

  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50">
        <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <span className="font-bold text-brand-700 text-lg tracking-tight">
                {appName}
              </span>
              <nav className="hidden sm:flex gap-4 text-sm text-slate-600">
                <a href="/"             className="hover:text-brand-600 transition-colors">Overview</a>
                <a href="/transactions" className="hover:text-brand-600 transition-colors">Transactions</a>
                <a href="/customers"    className="hover:text-brand-600 transition-colors">Customers</a>
                <a href="/quality"      className="hover:text-brand-600 transition-colors">Quality</a>
              </nav>
            </div>
            <span className="text-xs text-slate-400">
              Powered by PaySim · 6.36M rows
            </span>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
