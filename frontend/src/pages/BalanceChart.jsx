import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

const COLORS = [
  '#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#A28DFF', '#FF66C3', '#FFA07A', '#7FFFD4'
];

function BalanceChart({ data }) {
  const filteredData = data.filter(b => b.total_usd && b.total_usd > 0);

  return (
    <div className="mt-10 text-left">
      <h2 className="text-xl font-semibold mb-2 text-gray-800">📈 Distribución del portafolio</h2>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={filteredData}
            dataKey="total_usd"
            nameKey="asset"
            cx="50%"
            cy="50%"
            outerRadius={100}
            fill="#8884d8"
            label={(entry) => entry.asset}
          >
            {filteredData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(value) => `$${value.toFixed(2)}`} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export default BalanceChart;
