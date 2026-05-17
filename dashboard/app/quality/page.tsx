import QualityBadge from "../components/QualityBadge";

async function getData() {
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";
  const res = await fetch(`${base}/api/quality`, { next: { revalidate: 60 } });
  if (!res.ok) return null;
  return res.json();
}

export default async function QualityPage() {
  const data = await getData();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Data Quality</h1>
        <p className="text-slate-500 text-sm mt-1">
          Great Expectations validation results · 48 rules across 3 suites
        </p>
      </div>

      {data ? (
        <QualityBadge
          overall_status={data.overall_status}
          suites={data.suites}
          last_checked={data.last_checked}
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-400 text-sm">
          GX validation results not found. Run{" "}
          <code className="bg-slate-100 px-1 rounded">
            python great_expectations/run_validations.py all
          </code>{" "}
          to generate them.
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">
          Rule Coverage
        </h2>
        <div className="grid sm:grid-cols-3 gap-4 text-center">
          {[
            { layer: "Bronze Transactions", rules: 23, desc: "Null PKs, uniqueness, fraud flags, amount range, regex formats" },
            { layer: "Bronze Customers",    rules: 13, desc: "Segment validity, email format, KYC status, row count" },
            { layer: "Silver Transactions", rules: 12, desc: "Post-dbt completeness, type validity, amount range" },
          ].map((s) => (
            <div key={s.layer} className="rounded-lg bg-slate-50 p-4">
              <p className="text-2xl font-bold text-brand-700">{s.rules}</p>
              <p className="text-sm font-medium text-slate-700 mt-1">{s.layer}</p>
              <p className="text-xs text-slate-400 mt-1">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
