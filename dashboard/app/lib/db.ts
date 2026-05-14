import { Pool } from "pg";

// Singleton connection pool — reused across API route invocations.
// Next.js API routes run in Node.js; a new Pool per request would exhaust
// connections on RDS quickly. The singleton is safe here because Next.js
// server-side code runs in a single Node process.
let pool: Pool | null = null;

export function getPool(): Pool {
  if (!pool) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      max: 5,              // max 5 connections (RDS t3.micro limit is 22)
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 5_000,
    });
  }
  return pool;
}

export async function query<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const pool = getPool();
  const { rows } = await pool.query(sql, params);
  return rows as T[];
}
