import { NextResponse } from "next/server";
import { query } from "@/app/lib/db";

// GET /api/transactions
// Returns daily transaction volume by type for the past 30 days.
// Used by: TransactionChart (line chart) and KPI total volume card.
//
// This runs server-side only — the pg client and DATABASE_URL never
// leave the server. The browser only receives the JSON result.

export async function GET() {
  try {
    const rows = await query<{
      date: string;
      transaction_type: string;
      tx_count: number;
      total_volume: number;
      fraud_count: number;
    }>(`
      SELECT
        transaction_date::date                    AS date,
        transaction_type,
        COUNT(*)                                  AS tx_count,
        SUM(amount)                               AS total_volume,
        SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) AS fraud_count
      FROM main_gold.fact_transactions
      WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days'
      GROUP BY 1, 2
      ORDER BY 1 ASC, 2
    `);

    // Also return today's KPI totals
    const kpis = await query<{
      total_transactions: number;
      total_volume: number;
      fraud_transactions: number;
      avg_amount: number;
    }>(`
      SELECT
        COUNT(*)                                       AS total_transactions,
        COALESCE(SUM(amount), 0)                       AS total_volume,
        SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END)      AS fraud_transactions,
        COALESCE(AVG(amount), 0)                       AS avg_amount
      FROM main_gold.fact_transactions
    `);

    return NextResponse.json({
      daily:  rows,
      totals: kpis[0] ?? null,
    });
  } catch (err) {
    console.error("[/api/transactions]", err);
    return NextResponse.json(
      { error: "Failed to query transactions" },
      { status: 500 }
    );
  }
}
