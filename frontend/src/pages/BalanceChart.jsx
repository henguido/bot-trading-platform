import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = [
  "#22d3ee",
  "#34d399",
  "#818cf8",
  "#fbbf24",
  "#f472b6",
  "#a78bfa",
  "#38bdf8",
  "#fb7185",
];

function BalanceChart({ data }) {
  const filteredData = (data || []).filter(
    (item) => Number.isFinite(Number(item.total_usd)) && Number(item.total_usd) > 0,
  );

  if (filteredData.length === 0) {
    return (
      <div className="grid h-64 place-items-center">
        <div className="text-center">
          <p className="text-sm font-medium text-slate-400">Sin distribución disponible</p>
          <p className="mt-1 text-xs text-slate-600">No hay valores positivos que graficar.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={filteredData}
            dataKey="total_usd"
            nameKey="asset"
            cx="50%"
            cy="50%"
            innerRadius={58}
            outerRadius={92}
            paddingAngle={3}
            stroke="none"
          >
            {filteredData.map((entry, index) => (
              <Cell key={`${entry.asset}-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => [`$${Number(value).toFixed(2)}`, name]}
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: "12px",
              color: "#e2e8f0",
              fontSize: "12px",
            }}
            itemStyle={{ color: "#e2e8f0" }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export default BalanceChart;
