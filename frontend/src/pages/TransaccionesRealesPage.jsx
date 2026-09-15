import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/Card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getTransaccionesReales } from "../services/api";

const TransaccionesRealesPage = () => {
  const navigate = useNavigate();
  const [transacciones, setTransacciones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getTransaccionesReales()
      .then((data) => {
        setTransacciones(Array.isArray(data) ? data : []);
        setError("");
      })
      .catch((err) => {
        if (err.status === 401) {
          navigate("/login");
          return;
        }
        setError(err.message || "Error cargando transacciones reales");
      })
      .finally(() => setLoading(false));
  }, [navigate]);

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Historial de Transacciones Reales</h1>
      <Card>
        <CardContent className="overflow-auto p-4">
          {loading ? (
            <p>Cargando...</p>
          ) : error ? (
            <p className="text-red-600">{error}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Usuario</TableHead>
                  <TableHead>Símbolo</TableHead>
                  <TableHead>Operación</TableHead>
                  <TableHead>Cantidad</TableHead>
                  <TableHead>Precio</TableHead>
                  <TableHead>Fecha</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transacciones.map((tx) => (
                  <TableRow key={tx.id}>
                    <TableCell>{tx.id}</TableCell>
                    <TableCell>{tx.usuario_id}</TableCell>
                    <TableCell>{tx.simbolo}</TableCell>
                    <TableCell>{tx.tipo_operacion}</TableCell>
                    <TableCell>{tx.cantidad}</TableCell>
                    <TableCell>${tx.precio}</TableCell>
                    <TableCell>{tx.fecha}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default TransaccionesRealesPage;
