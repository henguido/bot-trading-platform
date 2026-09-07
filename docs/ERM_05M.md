# 05M Emergency Risk Monitor — diseño y aceptación

## Auditoría previa

Base GitHub revisada: PR #47 abierto/draft, HEAD
`43593fcdaa82dd750da847d1bc4aadb8d4887832`; main `d744820`.
La copia operativa local estaba en `0db29e6`. Desarrollo aislado en
`agent/erm-shadow-05m`, sin merge ni modificación de la rama del PR #47.
Se revisaron los chats disponibles de BOT Trading y los contratos de 05K,
MotorRiesgo, ejecución PAPER, cliente público, tests y CI. Baseline focal: 49 passed.

05K usa lotes por bucket y agrega coste para MotorRiesgo, pero rechaza símbolos
ya abiertos. Solo obtiene libros al abrir/cerrar (~4 h); no tiene trayectoria
intraminuto. `backend/risk/estado.py` importa persistencia: 05M no lo importa.
El modelo puro de fill PAPER sí es reutilizable, sin red ni DB.
La hipótesis 05I/05J/05K y su scheduler quedan congelados.

## Contrato y arquitectura predeclarados

1. Núcleo puro: ledger decimal por lote, indicadores causales, estados y gates.
2. Adaptador de lectura 05K BASE: identidad bucket/símbolo/apertura, nunca altera
   el archivo fuente. Cada entrada conserva fill, fees, cantidad y due_at.
3. Replay pareado: mismos lotes BASE en dos libros independientes; BASE vence
   según due_at y ERM puede cerrar antes. No reinvierte efectivo liberado ni
   inventa nuevas señales. Ampliaciones se validan en el ledger como capacidad
   independiente; no se activan en la hipótesis 05K.
4. Capturador REST público independiente, opcional y finito, cada 30 s mientras
   haya posiciones BASE pendientes; persiste únicamente evidencia 05M. Se usa
   REST inicialmente; WebSocket queda como adaptador futuro, sin simularlo.
5. CLI offline produce informe y auditoría JSON. CI ejecuta tests offline sin
   secretos ni scheduler ni trading loop.

Invariantes: SHADOW ONLY, PAPER 500 USDT, asignación <=2% del efectivo y <=10
USDT, LIVE=false, 05E=false, orders_executed=false, scanner_modified=false,
database_touched=false, llm_called=false. Ningún resultado autoriza promoción.
Límites adicionales 05M predeclarados: activo 50, portfolio 100 USDT (también
valorados a mercado), riesgo a stops 10 USDT portfolio; máximo diario realizado
20 USDT. Son guardas experimentales, no cambios de configuración productiva.

Contabilidad: promedio ponderado bruto y coste medio con fee separados.
P&L neto marcado incluye fee de entrada y fee estimada de salida; realizado usa
VWAP de bids y fee de salida. Slippage ya está en VWAP: se informa, no se cobra
de nuevo. Reducciones explícitas por lote conservan coste/fee proporcional,
realizado y remanente. MFE>=0/MAE<=0 por unidad y P&L neto acumulado del lote;
posición conserva extremos de precio desde apertura y desde última ampliación.
El drawdown de precio no se reinicia al ampliar; el de equity usa efectivo más
valor neto de liquidación, de modo que compras no crean beneficios artificiales.

Nueva entrada requiere señal explícita válida, única, vigente <=10 min, anterior
al instante de decisión; autorización de MotorRiesgo aportada por el consumidor,
fill dentro de ella y todos los límites locales. ADD_TO_WINNER exige P&L neto
actual positivo; cero/negativo es ADD_TO_LOSER. Una caída no genera señal.
PROTECT/EMERGENCY/COOLDOWN y datos degradados bloquean cualquier ampliación.

Indicadores: retornos de velas cerradas 1/5/10 min; desviación de log-retornos
de 30 min, ATR14, volumen relativo a 20 velas previas; spread y mediana histórica
de 20 libros, profundidad en ±1% del mid, imbalance de notional, VWAP/slippage
para cantidad real, drawdown de precio, riesgo remanente y pérdida neta.
Velas futuras, repetidas, gaps, book cruzado/no ordenado, precio no finito,
timestamps stale o fuera de orden invalidan datos. Desconocido permanece null.

Reglas iniciales congeladas antes de resultados (no parámetros validados):
movimiento adverso estandarizado max(-r_h/(sigma*sqrt(h))) con piso sigma=0.0005;
WATCH z>=2; PROTECT z>=3 más deterioro de liquidez/volumen, o retroceso >=1 ATR
después de ganancia >=2 ATR; EMERGENCY z>=5 más deterioro de liquidez.
Deterioro: spread >=3x mediana, imbalance<=-0.6 o slippage>=30 bps;
volumen anormal >=3x. Confirmaciones 2/3/2, separadas >=20 s y sin gaps >60 s.
El adaptador BASE asigna un stop experimental inicial del 3% bajo el fill;
05K no tiene stops que se puedan heredar. Este 3% no es el límite de asignación
2% y no está calibrado. El ledger acepta stops explícitos de la señal para
otros experimentos de lotes, sin modificar el adaptador BASE congelado.
Hard-stop por lote, presupuesto neto de pérdida o límite portfolio activa
EMERGENCY inmediatamente con precio fresco, aunque falten indicadores.
Precio stale no permite asumir ejecución. EMERGENCY persiste hasta cierre;
salida de WATCH/PROTECT requiere 4 lecturas sanas z<1 y sin deterioro/protección;
COOLDOWN mínimo 300 s más 4 lecturas sanas para NORMAL. Riesgo renovado interrumpe
COOLDOWN. PROTECT arma trailing virtual de 1 ATR; nunca baja un stop.

## Comparación y aceptación

Mismo evento temporal, libro, fees y filtros para ambos brazos; una salida ERM
decidida en t se llena como pronto en el siguiente snapshot válido (sin lookahead).
Sin profundidad suficiente/filtros/fee vigente no hay fill. BASE también usa
el primer snapshot válido en/después de due_at, señalando retraso de liquidación.
Cobertura incompleta se informa; no se atribuyen MFE/MAE completos a trayectorias
que empiezan tarde. No se hace backfill de order books usando velas.

Métricas: net P&L, equity max drawdown, pérdida media/máxima por lote, MAE/MFE,
fees, slippage USDT, delta pareado, pérdidas evitadas=max(delta,0) cuando BASE
pierde, ganancias protegidas=max(delta,0) cuando BASE gana, upside perdido=
max(-delta,0); falsa emergencia=salida EMERGENCY con BASE neto>=0 y delta<0.
Son contrafactuales con convención explícita, no una certeza causal. Se mantienen
denominadores, número de pares cerrados, cobertura y motivos no evaluables.
Sin pares completos: métricas comparativas null, INSUFFICIENT_EVIDENCE.
No declarar ventaja antes de 30 buckets completos y análisis prospectivo.

Aceptación comprobable: ejemplos 100/95 ponderados y fees; reducciones conservan
capital; señales duplicadas/stale y límites rechazan sin mutación; hard-stop
independiente de warmup; hysteresis, cooldown, gaps y recovery; indicadores
causales; salida siguiente tick, libros insuficientes, igualdad con ERM inactivo;
import 05K no muta fuente; CLI/replay deterministas; ninguna dependencia de DB,
LLM o broker en el núcleo; pruebas existentes y nuevas verdes; CI independiente.

Fuente del contrato de mercado público: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints

## Seguimiento

Mantener PR #47 draft; confirmar scheduler real separadamente; continuar 05I/J/K
hasta evidencia suficiente; renovar fee antes de 2026-09-11 18:47 UTC. Para 05M,
capturar trayectoria prospectiva completa y revisar resultados sin ajustar los
umbrales retrospectivamente. La implementación técnica no demuestra rentabilidad.

## Uso y límites operativos de esta entrega

Replay offline (directorio de salida nuevo, nunca sobrescribe otra evaluación):

```text
python scripts/shadow_emergency_risk_05m.py --source <estado-05k.json> --events <market-05m.jsonl> --output-dir <salida-nueva-05m>
```

Captura pública finita con evaluación durante cada observación:

```text
python scripts/shadow_emergency_risk_05m.py --source <estado-05k.json> --capture-seconds 15000 --fee-evidence <fee.json> --output-dir <captura-nueva-05m>
```

`fee.json` exige `bps`, `source` no vacío, `verified_at` y `expires_at` en segundos
Unix UTC; vigencia máxima 7 días, comprobada otra vez en cada fill. No lee claves
de Binance ni consulta cuentas. Conservar evidencia de verificación real.

Salidas: copia independiente de cohorte BASE, journal de mercado JSONL,
decisiones JSONL durante captura, informe final JSON con hashes y curvas equity.
El capturador sigue únicamente la cohorte abierta del snapshot inicial hasta
su vencimiento +60 s, sin incorporar compras posteriores silenciosamente.
Para una nueva cohorte se inicia una nueva captura independiente. Se conserva
BASE después de una salida temprana ERM para medir el contrafactual.
El capturador no se ha instalado como servicio ni se conecta al scanner.

Reinicio: repetir el replay de la copia de cohorte y journal produce ledger y
decisiones idénticos; no existen escrituras a DB ni un segundo estado mutable.
Un journal truncado se rechaza: no se completa una observación inventada.
La captura no reanuda automáticamente una conexión; conservar el journal previo
y evaluar cobertura explícitamente al reunir segmentos cronológicos.

Los primeros 20 libros forman el baseline de spread. Durante ese warmup la
política predeclarada es HOLD más hard-stop y bloqueo de ampliaciones. Si todos
los datos brutos están completos, estas observaciones son evaluables como esa
política y se contabilizan explícitamente en `warmup_samples`; no se presentan
como decisiones del monitor completo. Una captura iniciada más de 30 s después
de apertura o con datos brutos ausentes/gaps queda fuera de métricas comparativas
calificadas, aunque el hard-stop sigue funcionando. Los estados 05K históricos
por sí solos no pueden aportar trayectorias intraminuto.

El gate de nuevas entradas recibe la autorización explícita de MotorRiesgo del
consumidor; se prueba con el motor real, pero no se importa su reconstructor de
DB en el monitor. No genera señales, no evalúa noticias con GPT y no habilita
ampliaciones en el experimento BASE. Su integración a un servicio de producción
requiere otra fase autorizada después de evidencia.

Verificación local: 49 tests baseline, suite completa 1025 passed (413 warnings
preexistentes), 66 tests propios tras revisar liquidez consumida, reinicio,
estados y límites; compilación correcta. Los cambios posteriores de metadatos
y cobertura warmup se verificaron otra vez con los 66 tests focales.
Ver CI del commit final para la validación remota.

## Continuación: readiness y cohorte independiente

`--check-only` con `--source`, `--capture-seconds` y `--fee-evidence` hace
preflight sin red ni escrituras. Devuelve `BLOCKED` (exit 2),
`READY_DIAGNOSTIC_ONLY` o `READY_FULL_COVERAGE_POSSIBLE` (exit 0).
Una cohorte vencida/futura, mezcla de lotes vencidos y activos, o fee inválida
bloquea antes de crear archivos o consultar mercado. Entrada tardía, duración
insuficiente o fee que vence antes del horizonte se reportan como diagnósticas.
La captura vuelve a comprobarlo al iniciar y guarda el informe previo.

Se preparó un arranque opcional para una cohorte **independiente**:

```text
python scripts/run_erm_05m_prospective.py --fee-evidence <fee.json> --output-dir <cohorte-nueva-05m> --capture-seconds 15000
```

Reutiliza las funciones existentes 05I/05K sin editar sus archivos: diccionarios
nuevos en memoria, mismo Top20/Top5, mismo MotorRiesgo y horizonte. Exige 20
candidatos y cinco lotes BASE ejecutables, guarda hashes del código, evidencia
de fee y `research_stream=ERM_05M_INDEPENDENT`. Enlaza inmediatamente la captura
para minimizar el retraso desde apertura. No lee ni escribe los artefactos
acumulativos oficiales, no hace maduración/backfill de sus cohortes y sus
resultados **no deben sumarse** a los contadores oficiales 05I/J/K.
Debe ejecutarse como proceso nuevo; credenciales privadas vacías y URL de DB
en memoria antes de importar los adaptadores. No consulta ninguna base de datos.
No modifica el scheduler ni instala un servicio. Prepararlo no inicia una captura.

Seguimiento GitHub verificado el 2026-09-07: scheduler run `34105460968`, evento
`schedule`, success; restauró `research-05-state-34086697716-1`. Continuidad
05I=11/30, 05J=11/30, 05K=3/30; veredicto INSUFFICIENT_EVIDENCE. PR #47 y #50
permanecen draft/sin merge. La fee verificada mantiene su fecha original,
2026-09-04 18:47 UTC, y caduca el 2026-09-11 18:47 UTC; no se renovó su edad.
