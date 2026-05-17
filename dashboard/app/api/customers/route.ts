import { NextResponse } from "next/server";
import { query } from "@/app/lib/db";

// GET /api/customers
// Returns customer segment breakdown and KYC status distribution.
// Used by: Customers page donut chart and segment table.

export async function GET() {
  try {
    const segments = await query<{
      segment: string;
      customer_count: number;
      pct: number;
    }>(`
      SELECT
        segment,
        COUNT(DISTINCT customer_natural_key) AS customer_count,
        ROUND(
          COUNT(DISTINCT customer_natural_key) * 100.0
          / SUM(COUNT(DISTINCT customer_natural_key)) OVER (),
          1
        ) AS pct
      FROM main_gold.dim_customer
      WHERE is_current = true
      GROUP BY segment
      ORDER BY customer_count DESC
    `);

    const kyc = await query<{
      kyc_status: string;
      count: number;
    }>(`
      SELECT
        kyc_status,
        COUNT(*) AS count
      FROM main_silver.stg_customers
      GROUP BY kyc_status
      ORDER BY count DESC
    `);

    return NextResponse.json({ segments, kyc });
  } catch (err) {
    console.error("[/api/customers]", err);
    return NextResponse.json(
      { error: "Failed to query customers" },
      { status: 500 }
    );
  }
}
