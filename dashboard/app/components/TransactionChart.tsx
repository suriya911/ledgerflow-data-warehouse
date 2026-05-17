"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface DailyRow {
  date: string;
  transaction_type: string;
  tx_count: number;
  total_volume: number;
  fraud_count: number;
}

interface TransactionChartProps {
  data: DailyRow[];
}

const TYPE_COLORS: Record<string, string> = {
  CASH_OUT:  "#3b82f6",
  PAYMENT:   "#10b981",
  CASH_IN:   "#f59e0b",
  TRANSFER:  "#8b5cf6",
  DEBIT:     "#ef4444",
};

export default function TransactionChart({ data }: TransactionChartProps) {
  // Pivot: one row per date, one key per transaction_type
  const byDate: Record<string, Record<string, number>> = {};
  for (const row of data) {
    if (!byDate[row.date]) byDate[row.date] = { date: row.date as unknown as number };
    byDate[row.date][row.transaction_type] = Number(row.tx_count);
  }

  const chartData = Object.values(byDate).sort((a, b) =>
    String(a.date).localeCompare(String(b.date))
  );

  const types = Array.from(new Set(data.map((r) => r.transaction_type)));

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
        No transaction data for the past 30 days
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickFormatter={(v) => String(v).slice(5)}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickFormatter={(v) =>
            v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v
          }
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
          formatter={(value: number, name: string) => [
            value.toLocaleString(),
            name,
          ]}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {types.map((type) => (
          <Line
            key={type}
            type="monotone"
            dataKey={type}
            stroke={TYPE_COLORS[type] ?? "#64748b"}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
