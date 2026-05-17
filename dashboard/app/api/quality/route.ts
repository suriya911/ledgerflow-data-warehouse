import { NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

// GET /api/quality
// Returns the latest Great Expectations validation results.
// Reads the GX validation JSON files from the filesystem (local dev)
// or from S3 (prod — when USE_S3=true).
//
// GX writes validation results to:
//   great_expectations/uncommitted/validations/<suite>/<run_id>/
//
// For the dashboard we summarise: suite name, pass/fail, counts, timestamp.

interface SuiteResult {
  suite: string;
  success: boolean;
  evaluated_expectations: number;
  successful_expectations: number;
  failed_expectations: number;
  run_time: string | null;
}

function readLocalValidations(): SuiteResult[] {
  const suites = [
    "bronze_transactions",
    "bronze_customers",
    "silver_transactions",
  ];

  const results: SuiteResult[] = [];

  for (const suite of suites) {
    const validationsDir = join(
      process.cwd(),
      "..",
      "great_expectations",
      "uncommitted",
      "validations",
      suite
    );

    if (!existsSync(validationsDir)) {
      results.push({
        suite,
        success: false,
        evaluated_expectations: 0,
        successful_expectations: 0,
        failed_expectations: 0,
        run_time: null,
      });
      continue;
    }

    // Find the most recent run directory (sorted by name = chronological)
    const { readdirSync } = require("fs");
    const runs: string[] = readdirSync(validationsDir).sort().reverse();

    if (runs.length === 0) {
      results.push({
        suite,
        success: false,
        evaluated_expectations: 0,
        successful_expectations: 0,
        failed_expectations: 0,
        run_time: null,
      });
      continue;
    }

    const latestRun = runs[0];
    const runDir = join(validationsDir, latestRun);
    const files: string[] = readdirSync(runDir).filter((f: string) =>
      f.endsWith(".json")
    );

    if (files.length === 0) continue;

    try {
      const content = readFileSync(join(runDir, files[0]), "utf-8");
      const data = JSON.parse(content);
      const stats = data.statistics ?? {};

      results.push({
        suite,
        success: data.success ?? false,
        evaluated_expectations: stats.evaluated_expectations ?? 0,
        successful_expectations: stats.successful_expectations ?? 0,
        failed_expectations: stats.unsuccessful_expectations ?? 0,
        run_time: data.meta?.run_id?.run_time ?? null,
      });
    } catch {
      results.push({
        suite,
        success: false,
        evaluated_expectations: 0,
        successful_expectations: 0,
        failed_expectations: 0,
        run_time: null,
      });
    }
  }

  return results;
}

export async function GET() {
  try {
    const results = readLocalValidations();
    const allPassed = results.every((r) => r.success);

    return NextResponse.json({
      overall_status: allPassed ? "PASS" : "FAIL",
      suites: results,
      last_checked: new Date().toISOString(),
    });
  } catch (err) {
    console.error("[/api/quality]", err);
    return NextResponse.json(
      { error: "Failed to read GX validation results" },
      { status: 500 }
    );
  }
}
