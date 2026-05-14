import TransactionChart from "../components/TransactionChart";

async function getData() {
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";
  const res = await fetch(`${base}/api/transactions`, { next: { revalidate: 300 } });
  if (!res.ok) return null;
  return res.json();
}

export default async function TransactionsPage() {
  const data = await getData();
  const daily = data?.daily ?? [];
  const totals = data?.totals;

  // Aggregate totals by type from daily rows
  const byType: Record<string, { count: number; volume: number; fraud: number }> = {};
  for (const row of daily) {
    if (!byType[row.transaction_type]) {
      byType[row.transaction_type] = { count: 0, volume: 0, fraud: 0 };
    }
    byType[row.transaction_type].count  += Number(row.tx_count);
    byType[row.transaction_type].volume += Number(row.total_volume);
    byType[row.transaction_type].fraud  += Number(row.fraud_count);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Transactions</h1>
        <p className="text-slate-500 text-sm mt-1">
          Daily volume by type · past 30 days
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <TransactionChart data={daily} />
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-5 py-3 text-left">Type</th>
              <th className="px-5 py-3 text-right">Count (30d)</th>
              <th className="px-5 py-3 text-right">Volume (30d)</th>
              <th className="px-5 py-3 text-right">Fraud</th>
              <th className="px-5 py-3 text-right">Fraud Rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {Object.entries(byType)
              .sort(([, a], [, b]) => b.count - a.count)
              .map(([type, stats]) => (
                <tr key={type} className="hover:bg-slate-50">
                  <td className="px-5 py-3 font-medium text-slate-700">{type}</td>
                  <td className="px-5 py-3 text-right text-slate-600">
                    {stats.count.toLocaleString()}
                  </td>
                  <td className="px-5 py-3 text-right text-slate-600">
                    ${(stats.volume / 1_000_000).toFixed(1)}M
                  </td>
                  <td className="px-5 py-3 text-right text-red-600">
                    {stats.fraud.toLocaleString()}
                  </td>
                  <td className="px-5 py-3 text-right text-slate-500">
                    {stats.count > 0
                      ? ((stats.fraud / stats.count) * 100).toFixed(2) + "%"
                      : "—"}
                  </td>
                </tr>
              ))}
          </tbody>
          {totals && (
            <tfoot className="bg-slate-50 font-semibold text-slate-700 text-xs">
              <tr>
                <td className="px-5 py-3">ALL TIME TOTAL</td>
                <td className="px-5 py-3 text-right">
                  {Number(totals.total_transactions).toLocaleString()}
                </td>
                <td className="px-5 py-3 text-right">
                  ${(Number(totals.total_volume) / 1_000_000_000).toFixed(2)}B
                </td>
                <td className="px-5 py-3 text-right text-red-600">
                  {Number(totals.fraud_transactions).toLocaleString()}
                </td>
                <td className="px-5 py-3 text-right">
                  {(
                    (Number(totals.fraud_transactions) /
                      Number(totals.total_transactions)) *
                    100
                  ).toFixed(3)}%
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
