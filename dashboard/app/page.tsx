// KPI overview — server component fetches data at request time
// (no client-side fetch needed for the initial load)

import KpiCards from "./components/KpiCards";
import TransactionChart from "./components/TransactionChart";
import QualityBadge from "./components/QualityBadge";

async function getTransactions() {
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";
  const res = await fetch(`${base}/api/transactions`, {
    next: { revalidate: 300 }, // cache for 5 min, revalidate in background
  });
  if (!res.ok) return null;
  return res.json();
}

async function getQuality() {
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";
  const res = await fetch(`${base}/api/quality`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) return null;
  return res.json();
}

export default async function HomePage() {
  const [txData, qualityData] = await Promise.all([
    getTransactions(),
    getQuality(),
  ]);

  const totals = txData?.totals ?? {
    total_transactions: 0,
    total_volume: 0,
    fraud_transactions: 0,
    avg_amount: 0,
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Overview</h1>
        <p className="text-slate-500 text-sm mt-1">
          LedgerFlow data warehouse · PaySim 6.36M transaction dataset
        </p>
      </div>

      <KpiCards
        totalTransactions={Number(totals.total_transactions)}
        totalVolume={Number(totals.total_volume)}
        fraudTransactions={Number(totals.fraud_transactions)}
        avgAmount={Number(totals.avg_amount)}
      />

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">
          Daily Transaction Volume by Type (past 30 days)
        </h2>
        <TransactionChart data={txData?.daily ?? []} />
      </div>

      {qualityData && (
        <div>
          <h2 className="text-sm font-semibold text-slate-700 mb-3">
            Data Quality Gates
          </h2>
          <QualityBadge
            overall_status={qualityData.overall_status}
            suites={qualityData.suites}
            last_checked={qualityData.last_checked}
          />
        </div>
      )}
    </div>
  );
}
