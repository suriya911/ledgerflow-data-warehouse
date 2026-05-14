"use client";

import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";

const SEGMENT_COLORS: Record<string, string> = {
  RETAIL:    "#3b82f6",
  PREMIUM:   "#8b5cf6",
  CORPORATE: "#10b981",
};

const KYC_COLORS: Record<string, string> = {
  VERIFIED: "#10b981",
  PENDING:  "#f59e0b",
  FAILED:   "#ef4444",
  EXPIRED:  "#94a3b8",
};

export default function CustomersPage() {
  const [data, setData] = useState<{
    segments: { segment: string; customer_count: number; pct: number }[];
    kyc: { kyc_status: string; count: number }[];
  } | null>(null);

  useEffect(() => {
    fetch("/api/customers")
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, []);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        Loading...
      </div>
    );
  }

  const segmentData = data.segments.map((s) => ({
    name: s.segment,
    value: Number(s.customer_count),
  }));

  const kycData = data.kyc.map((k) => ({
    name: k.kyc_status,
    value: Number(k.count),
  }));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Customers</h1>
        <p className="text-slate-500 text-sm mt-1">
          Segment breakdown · KYC status distribution
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">
            Customer Segments (current)
          </h2>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={segmentData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                dataKey="value"
                label={({ name, pct }: { name: string; pct: number }) =>
                  `${name} ${pct}%`
                }
              >
                {segmentData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={SEGMENT_COLORS[entry.name] ?? "#64748b"}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => v.toLocaleString()} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">
            KYC Status
          </h2>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={kycData}
                cx="50%"
                cy="50%"
                outerRadius={90}
                dataKey="value"
              >
                {kycData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={KYC_COLORS[entry.name] ?? "#64748b"}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => v.toLocaleString()} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-5 py-3 text-left">Segment</th>
              <th className="px-5 py-3 text-right">Customers</th>
              <th className="px-5 py-3 text-right">Share</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.segments.map((s) => (
              <tr key={s.segment} className="hover:bg-slate-50">
                <td className="px-5 py-3 font-medium text-slate-700">
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-2"
                    style={{ background: SEGMENT_COLORS[s.segment] ?? "#64748b" }}
                  />
                  {s.segment}
                </td>
                <td className="px-5 py-3 text-right text-slate-600">
                  {Number(s.customer_count).toLocaleString()}
                </td>
                <td className="px-5 py-3 text-right text-slate-500">
                  {s.pct}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
