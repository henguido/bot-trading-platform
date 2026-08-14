import React from "react";

export const Table = ({ children, className = "" }) => (
  <table className={`min-w-full border border-gray-300 ${className}`}>{children}</table>
);

export const TableHeader = ({ children }) => (
  <thead className="bg-gray-100 text-left">{children}</thead>
);

export const TableBody = ({ children }) => <tbody>{children}</tbody>;

export const TableRow = ({ children }) => (
  <tr className="border-b last:border-b-0 hover:bg-gray-50">{children}</tr>
);

export const TableHead = ({ children }) => (
  <th className="px-4 py-2 text-sm font-semibold text-gray-600">{children}</th>
);

export const TableCell = ({ children }) => (
  <td className="px-4 py-2 text-sm text-gray-800">{children}</td>
);
