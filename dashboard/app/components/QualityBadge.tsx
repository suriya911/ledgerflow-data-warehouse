"use client";

interface SuiteResult {
  suite: string;
  success: boolean;
  evaluated_expectations: number;
  successful_expectations: number;
  failed_expectations: number;
  run_time: string | null;
}

interface QualityBadgeProps {
  overall_status: string;
  suites: SuiteResult[];
  last_checked: string;
}

function Badge({ success }: { success: boolean }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${
        success
          ? "bg-emerald-100 text-emerald-700"
          : "bg-red-100 text-red-700"
      }`}
    >
      {success ? "PASS" : "FAIL"}
    </span>
  );
}

export default function QualityBadge({
  overall_status,
  suites,
  last_checked,
}: QualityBadgeProps) {
  const isOk = overall_status === "PASS";

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div
        className={`px-5 py-3 flex items-center justify-between ${
          isOk ? "bg-emerald-50" : "bg-red-50"
        }`}
      >
        <div className="flex items-center gap-2">
          <span className={`text-xl font-bold ${isOk ? "text-emerald-700" : "text-red-700"}`}>
            {isOk ? "All quality gates passing" : "Quality gate failure detected"}
          </span>
        </div>
        <Badge success={isOk} />
      </div>

      <div className="divide-y divide-slate-100">
        {suites.map((suite) => (
          <div key={suite.suite} className="px-5 py-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-700">
                {suite.suite.replace(/_/g, " ")}
              </p>
              {suite.run_time && (
                <p className="text-xs text-slate-400">
                  Last run: {new Date(suite.run_time).toLocaleString()}
                </p>
              )}
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-slate-500">
                {suite.successful_expectations}/{suite.evaluated_expectations} rules
              </span>
              <Badge success={suite.success} />
            </div>
          </div>
        ))}
      </div>

      <div className="px-5 py-2 bg-slate-50 text-xs text-slate-400 border-t border-slate-100">
        Checked: {new Date(last_checked).toLocaleString()}
      </div>
    </div>
  );
}
