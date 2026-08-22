# BOT 2.0 — 04E-3 Auditoría comparativa de fuentes de yield públicas

## Estado

**PREDECLARADO ANTES DEL INVENTARIO S3 REAL. NO HAY PnL, RETORNOS NI PRIMAS.**

Después de 04E-2, la prioridad es no abrir otra hipótesis cuyo reward histórico dependa de USER_DATA, una API key privada o un proxy de precio. 04E-3 compara fuentes por reproducibilidad técnica antes de cualquier estrategia.

## Candidatos

### 1. Binance Options

Binance Data Collection (`data.binance.vision`) expone una raíz pública `data/option/`. La auditoría fija el prefijo `data/option/daily/EOHSummary/` y solo inventaría metadata S3: keys, tamaños y fechas. No descarga ZIPs en 04E-3.

Gate predeclarado para pasar a una futura auditoría de contenido:

- listado S3 completo;
- al menos 350 días distintos en cada año 2022, 2023, 2024 y 2025;
- cero ZIPs de tamaño cero;
- cero keys duplicados;
- periodo 2026 excluido del conteo económico;
- transferencia comprimida 2022-2025 cuantificada antes de descargar contenido.

Un resultado apto solo significa **archivo histórico disponible**. No significa que una estrategia de opciones tenga edge ni que EOHSummary contenga todos los campos necesarios; eso requeriría una etapa de contenido separada y predeclarada.

### 2. Lido stETH

La documentación oficial de Lido define la mecánica de share rate y la fórmula de APR de V2 usando `TokenRebased`. También documenta que para despliegues legacy el APR se obtenía de eventos de reportes del oracle. Su subgraph incluye `totalRewards`, pooled ETH/shares, APR y timestamps históricos.

La limitación operativa actual es transporte: el endpoint oficial documentado del subgraph contiene `[api-key]`, y las APIs read-only directas documentadas exponen APR actual/SMA y reward history por dirección, no una serie global histórica sin key para 2022-2025.

Por tanto 04E-3 clasifica Lido como:

`LIDO_SEMANTICA_APTA_TRANSPORTE_HISTORICO_SIN_KEY_NO_VERIFICADO_04E3`

Esto no falsifica Lido. Solo impide declararlo listo para la siguiente etapa bajo el gate zero-secret/zero-infrastructure actual.

### 3. Aave lending

Aave V3 emite `ReserveDataUpdated(reserve, liquidityRate, ..., liquidityIndex, ...)`; el core documenta además que el liquidity index acumula el ingreso de proveedores. La semántica de yield es auditable on-chain.

04E-3 no predeclara un archivo HTTP oficial/no-key 2022-2025 para esos eventos. Indexarlos mediante un RPC/subgraph de terceros sería una decisión de infraestructura aparte, que no se introduce silenciosamente en este experimento.

Estado:

`AAVE_SEMANTICA_APTA_TRANSPORTE_HISTORICO_SIN_KEY_NO_VERIFICADO_04E3`

## Gate común para avanzar

Una fuente debe tener:

1. cobertura 2022-2025;
2. acceso sin API key/secreto;
3. mecánica de yield/payoff exacta, no proxy de precio;
4. timestamps/settlement auditables;
5. transferencia histórica acotable antes de descargar contenido.

## Prohibiciones

- `PNL_PERMITIDO_04E3=False`.
- no descargar contenido de Options en esta etapa;
- no API keys ni credenciales;
- no PAPER operativo, LIVE ni Render;
- 2026 cerrado;
- no imputar APR/yield;
- no usar precio secundario como reward;
- no escoger una fuente por su rentabilidad observada.

## Decisión predeclarada

Si Binance Options supera el gate de inventario y Lido/Aave no verifican transporte histórico oficial sin key, Options será el único candidato habilitado **solo para una auditoría de contenido**, no para backtest.

Si Options no supera cobertura, 04E-3 se cerrará sin candidato y se deberá resolver primero una fuente histórica reproducible; no se relajarán fechas ni umbrales retrospectivamente.
