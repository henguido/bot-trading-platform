# BOT 2.0 — 04E-3 Resultado auditoría de fuentes de yield públicas

## Veredicto

**No hay candidato habilitado para la siguiente etapa bajo los gates 04E-3.**

- Binance Options: `OPTIONS_ARCHIVO_PUBLICO_INCOMPLETO_04E3`
- Lido stETH: `LIDO_SEMANTICA_APTA_TRANSPORTE_HISTORICO_SIN_KEY_NO_VERIFICADO_04E3`
- Aave lending: `AAVE_SEMANTICA_APTA_TRANSPORTE_HISTORICO_SIN_KEY_NO_VERIFICADO_04E3`
- `candidates_apt_for_next_stage=[]`
- PnL calculado: no.
- Contenido Options descargado: no.
- Credenciales usadas: no.
- 2026 abierto: no.

## Binance Options — inventario real

Prefijo auditado, fijado antes del listado real:

`data/option/daily/EOHSummary/`

Resultado S3:

- listado completo: sí;
- páginas: 2;
- ZIPs: 545;
- ZIPs tamaño cero: 0;
- keys duplicados: 0;
- primera fecha: `2023-05-18`;
- última fecha: `2023-10-23`;
- tamaño comprimido dentro de 2022-2025: `0.129717 GiB`;
- días distintos 2022: 0;
- días distintos 2023: 147;
- días distintos 2024: 0;
- días distintos 2025: 0.

Gate predeclarado: al menos 350 días distintos por cada año 2022-2025. Falla los cuatro años.

### Nota de conservadurismo sobre el prefijo

Después del run se verificó que EOHSummary puede particionarse por subyacente, por ejemplo `.../EOHSummary/BTCUSDT/`. No se cambia el protocolo ni se repite con un subyacente elegido retrospectivamente.

El prefijo padre usado en 04E-3 es más permisivo porque agrega objetos de todos los subyacentes. Aun así muestra cero días en 2022, 2024 y 2025 y solo 147 en 2023. Restringir a BTCUSDT u otro subyacente solo podría mantener o reducir esos conteos; no puede rescatar cobertura 2022-2025. Por tanto el veredicto es robusto y no requiere rerun post hoc.

Artifact del primer inventario real:

- `public-yield-source-audit-04e3`
- ID `9466829883`
- SHA256 `eebf3ea9ac98856104dfaa9280af19fa2330c1f83ba62b8192d3659f30105ba4`

## Lido stETH

La mecánica económica sí es reconstruible de manera exacta desde share rate/oracle reports. Lido documenta para V2+ la fórmula basada en `TokenRebased`; para legacy indica que el APR se obtenía consultando eventos de reportes del oracle. El subgraph expone `totalRewards`, pooled ETH/shares, APR, block y blockTime.

Sin embargo, el endpoint oficial documentado del subgraph contiene `[api-key]`. Las APIs read-only directas documentadas exponen APR actual/SMA y reward history por dirección, no una serie global histórica 2022-2025 zero-key.

Acceder directamente a Ethereum tampoco resuelve automáticamente el gate zero-infrastructure: proveedores públicos pueden limitar/gatear consultas de archivo. 04E-3 no introduce un proveedor externo ni una API key después de observar esta limitación.

Conclusión Lido: semántica apta; transporte histórico oficial/no-key no verificado; no habilitado para backtest.

## Aave lending

Aave documenta `ReserveDataUpdated` con `liquidityRate` y `liquidityIndex`; el core define cómo el liquidity index acumula el ingreso de proveedores. La semántica del yield es exacta y on-chain.

No se verificó en 04E-3 un archivo HTTP histórico oficial/no-key 2022-2025. Recuperar años de eventos mediante RPC/subgraph requiere escoger infraestructura de indexación/archivo, decisión que no se introduce post hoc en este experimento.

Conclusión Aave: semántica apta; transporte histórico oficial/no-key no verificado; no habilitado para backtest.

## Validación

Primer run real `research-04e3` #2:

- methodology locks: success;
- tests específicos: 4/4 passed;
- inventario S3: success técnico;
- artifact upload: success;
- CI general #132: success.

## Decisión metodológica

04E-3 cierra la búsqueda inmediata de una nueva fuente de **yield** dentro del gate actual de datos públicos 2022-2025, zero-secret y zero-infrastructure.

No se harán estas acciones para rescatar la línea:

1. cambiar a otro subyacente Options después de ver la cobertura;
2. reducir el periodo a 2023;
3. abrir 2026;
4. usar una API key de The Graph/RPC archive;
5. imputar APR de Lido/Aave desde terceros;
6. convertir un precio secundario en proxy de reward.

Esto no demuestra que Lido/Aave carezcan de edge. Demuestra que no cumplen el estándar de reproducibilidad definido para esta etapa.

La siguiente investigación debe salir de la familia de yield y volver a una fuente independiente con dataset público ya auditado. El candidato natural es **order flow AggTrades**, cuyo inventario/formato real ya fue validado previamente, en lugar de seguir relajando requisitos para encontrar yield.

Cierre previsto: sin merge a `main`, sin PAPER operativo, sin LIVE, sin Render y con 2026 cerrado.
