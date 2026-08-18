import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/Card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const TransaccionesRealesPage = () => {
  const [transacciones, setTransacciones] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/api/transacciones-reales")
      .then((res) => res.json())
      .then((data) => {
        setTransacciones(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error cargando transacciones reales:", err);
        setLoading(false);
      });
  }, []);

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Historial de Transacciones Reales</h1>
      <Card>
        <CardContent className="overflow-auto p-4">
          {loading ? (
            <p>Cargando...</p>
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