"use client";

interface KpiCardsProps {
  totalTransactions: number;
  totalVolume: number;
  fraudTransactions: number;
  avgAmount: number;
}

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
}

function currency(n: number): string {
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000)     return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)         return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

interface CardProps {
  label: string;
  value: string;
  sub: string;
  color: string;
}

function Card({ label, value, sub, color }: CardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-1 shadow-sm">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
        {label}
      </span>
      <span className={`text-3xl font-bold ${color}`}>{value}</span>
      <span className="text-xs text-slate-400">{sub}</span>
    </div>
  );
}

export default function KpiCards({
  totalTransactions,
  totalVolume,
  fraudTransactions,
  avgAmount,
}: KpiCardsProps) {
  const fraudPct =
    totalTransactions > 0
      ? ((fraudTransactions / totalTransactions) * 100).toFixed(3)
      : "0";

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        label="Total Transactions"
        value={fmt(totalTransactions)}
        sub="PaySim mobile money dataset"
        color="text-slate-800"
      />
      <Card
        label="Total Volume"
        value={currency(totalVolume)}
        sub="All-time transaction value"
        color="text-brand-700"
      />
      <Card
        label="Fraud Rate"
        value={`${fraudPct}%`}
        sub={`${fmt(fraudTransactions)} confirmed fraud txns`}
        color="text-red-600"
      />
      <Card
        label="Avg Transaction"
        value={currency(avgAmount)}
        sub="Mean amount across all types"
        color="text-slate-700"
      />
    </div>
  );
}
