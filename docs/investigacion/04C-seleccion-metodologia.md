# BOT 2.0 — 04C Selección de metodología antes de backtest

## Estado

**DISEÑO / REVISIÓN DE EVIDENCIA — sin backtest 04C y sin abrir 2026.**

04B queda cerrado como fase de falsación de señales direccionales. El objetivo de 04C es cambiar el orden del proceso: primero seleccionar una metodología por evidencia externa, mecanismo económico, viabilidad operativa y costos; después auditar datos; solo entonces predeclarar una prueba económica.

No se declara ninguna estrategia rentable ex ante. La evidencia externa sirve para elevar la probabilidad previa y reducir grados de libertad, no para sustituir validación propia.

## Criterios de selección

Una metodología candidata debe cumplir, antes de backtest interno:

1. **Mecanismo económico identificable:** debe existir una explicación de quién paga la prima y por qué puede persistir.
2. **Evidencia externa independiente:** prioridad a trabajos revisados por pares, BIS y evidencia con muestras amplias.
3. **Implementabilidad en Binance:** instrumentos, market data y ejecución deben estar disponibles por interfaces soportadas.
4. **Rentabilidad evaluable neta de costos:** fees, spread, slippage, funding, collateral y margen deben formar parte del modelo antes del resultado.
5. **Baja libertad de ajuste:** la especificación inicial debe poder fijarse sin buscar combinaciones retrospectivas.
6. **Riesgo controlable:** la fuente de retorno debe poder separarse de exposición direccional no deseada.
7. **Compatibilidad con la arquitectura actual:** se evita convertir el proyecto en un motor HFT si no es indispensable.

## Candidato 1 — Carry delta-neutral Spot + Futures

### Evidencia

Schmeling, Schrimpf y Todorov, *Crypto Carry*, publicado en Management Science el 6 de mayo de 2026 y previamente como BIS Working Paper 1087, documenta que el basis entre futuros y spot puede alcanzar niveles excepcionalmente altos, en ocasiones superiores al 40% anualizado, y que el carry medio estudiado es muy superior al de otras clases de activos.

El mecanismo propuesto no depende de predecir la dirección de BTC/ETH: la demanda de exposición apalancada de inversores trend-chasing y la escasez relativa de capital de arbitraje, limitada por regulación y restricciones de margen, sostienen diferencias entre futuros y spot.

Referencia primaria:
- Schmeling, M.; Schrimpf, A.; Todorov, K. (2026), “Crypto Carry”, Management Science. DOI: 10.1287/mnsc.2024.05069.
- BIS Working Paper 1087, revisión octubre de 2025.

Fan, Jiao, Lu y Tong documentan además una estrategia cross-sectional de carry en criptomonedas con 43,4% anualizado y Sharpe 0,74 en su muestra, aunque es evidencia de working paper y no se adopta su cifra como expectativa para este BOT.

### Forma operacional preferida

#### A. Cash-and-carry con futuros fechados

Cuando un futuro cotiza suficientemente por encima del Spot:

- comprar Spot;
- vender/short el futuro por notional equivalente;
- mantener delta aproximada a cero;
- capturar convergencia del basis hacia vencimiento;
- cerrar o liquidar según protocolo predefinido.

La fuente esperada de retorno es la convergencia del basis, no el movimiento absoluto del activo.

Esta variante se prioriza sobre perpetual funding porque el vencimiento proporciona un ancla temporal de convergencia. No elimina riesgos de margen, ejecución, exchange, basis intraperiodo ni liquidación.

#### B. Spot + short perpetual funding carry

Cuando funding positivo esperado compensa holgadamente fees, slippage y reserva de riesgo:

- long Spot;
- short perpetual por notional equivalente;
- recibir funding mientras persista;
- salida bajo reglas predeclaradas de funding/basis/margen.

Es más flexible y cubre más símbolos, pero funding puede cambiar de signo, por lo que se considera segunda variante de carry.

### Economía mínima a modelar antes del backtest

Para dated futures:

`carry_neto_esperado = basis_a_vencimiento - fees_spot - fees_futures - slippage - coste_colateral - reserva_riesgo`

Para perpetual:

`carry_neto_esperado = funding_acumulado_esperado + cambio_basis - fees_spot - fees_perp - slippage - coste_colateral - reserva_riesgo`

No se permitirá sustituir costos reales por un hurdle arbitrario cuando los componentes puedan obtenerse de Binance.

### Riesgos obligatorios

- descalce de notional y delta;
- liquidación de la pata short por margen insuficiente;
- expansión temporal del basis;
- funding que cambia de signo;
- fees maker/taker reales del usuario;
- slippage y profundidad;
- riesgo de exchange/custodia;
- cambios contractuales o de intervalo de funding;
- activos sin Spot equivalente o con liquidez insuficiente;
- vencimientos y rollovers;
- restricciones regulatorias/de cuenta que deben verificarse antes de cualquier uso real.

### Evaluación

**Prioridad: 1 — recomendada para 04C.**

Razones:

- retorno estructural, no forecast direccional;
- evidencia revisada por pares y BIS;
- Binance ofrece Spot, USDⓈ-M perpetuals y COIN-M perpetual/delivery futures mediante APIs documentadas;
- la arquitectura de riesgo/costos existente puede evolucionar sin requerir HFT;
- permite diseñar una posición market-neutral y medir cada componente económico.

## Candidato 2 — Lead-lag cross-crypto de alta frecuencia

Guo, Sang, Tu y Wang (Journal of Economic Dynamics and Control, 2024) encuentran predictibilidad cross-crypto en datos Binance a frecuencia de minutos. Retornos rezagados de otras criptomonedas, especialmente BTC, predicen retornos focales; adaptive LASSO y PCA sostienen resultados out-of-sample y los autores reportan portafolios long-short positivos después de costos en su diseño.

Mecanismo: difusión lenta de shocks comunes y atención limitada de participantes.

Problema para este BOT:

- requiere datos de minuto/subminuto;
- reequilibrio muy frecuente;
- shorting y ejecución precisa;
- costos y latencia dominan el edge;
- un pipeline con GPT o ciclos batch no es adecuado.

**Prioridad: 2 — evidencia fuerte, pero exigiría un motor de ejecución especializado de baja latencia.**

Referencia: Guo, L.; Sang, B.; Tu, J.; Wang, Y. (2024), “Cross-cryptocurrency return predictability”, Journal of Economic Dynamics and Control 163, 104863. DOI: 10.1016/j.jedc.2024.104863.

## Candidato 3 — Low-variance / variance cross-sectional semanal

Lee y Wang encuentran que criptomonedas con mayor varianza realizada presentan retornos inferiores en semanas posteriores. El efecto es más fuerte en activos pequeños, baratos, menos líquidos y con mayor participación retail.

Ventajas:

- frecuencia semanal;
- menor necesidad de infraestructura;
- construcción transparente y reproducible.

Limitación principal para el BOT actual:

- nuestro universo fijo y líquido de 20 activos puede ser precisamente donde el efecto sea más débil;
- ampliarlo exige reconstruir universo histórico sin survivorship y modelar capacidad de shorting/liquidez.

**Prioridad: 3 — candidato de respaldo, no primera opción.**

Referencia: Lee, S. S.; Wang, M. (2025), “Variance Decomposition and Cryptocurrency Return Prediction”, Journal of Financial and Quantitative Analysis 60(4), 1859-1890. DOI: 10.1017/S002210902400022X.

## Familias que NO se priorizan

### Precio/momentum puro

04B ya reunió evidencia interna suficiente para no seguir buscando percentiles, ventanas o signos alternativos en la misma familia.

### Funding/basis como predictor direccional

Los experimentos 04B con premium, basis y funding no demostraron edge direccional robusto. Esto **no invalida carry**: usar basis/funding como flujo económico de una posición hedged es una pregunta distinta de usarlos para predecir el retorno Spot futuro.

### ML genérico sobre muchas features

No se prioriza antes de encontrar una prima económica porque aumenta grados de libertad y riesgo de overfitting.

### Market making

Puede tener fundamentos estructurales, pero exige gestión de inventario, colocación/cancelación de órdenes, latencia, adverse selection y queue position que la arquitectura actual no cubre adecuadamente.

## Nuevo funnel obligatorio de investigación

A partir de 04C, el orden es:

1. evidencia externa y mecanismo económico;
2. viabilidad de instrumentos y datos;
3. auditoría histórica sin retornos de estrategia;
4. modelo de costos/riesgo fijado antes del resultado;
5. protocolo económico predeclarado;
6. réplica histórica de desarrollo 2022-2025;
7. si pasa: validaciones de robustez predefinidas;
8. holdout 2026 solo cuando corresponda y una vez cerrado el desarrollo;
9. PAPER operativo;
10. LIVE con capital mínimo únicamente si todos los gates previos pasan.

No se brincan etapas por un resultado atractivo.

## Próximo gate propuesto — 04C-0 auditoría de Carry

Antes de calcular una sola rentabilidad de estrategia, auditar:

- contratos Spot + Futures emparejables históricamente;
- dated/delivery futures y fechas de vencimiento disponibles;
- historical mark/index/futures prices;
- funding history e intervalos efectivos;
- cambios de caps/floors/intervalos;
- comisiones aplicables y qué parte puede reconstruirse históricamente;
- profundidad/liquidez disponible o proxies conservadores;
- mecanismos de liquidación y margen relevantes;
- cobertura 2022-2025;
- capacidad de construir posiciones delta-neutral sin imputación.

04C-0 no calculará PnL de carry ni seleccionará thresholds rentables.

## Candados

- 2026 cerrado;
- mayo-julio 2026 cerrado;
- sin PAPER operativo;
- sin LIVE;
- sin Render;
- sin credenciales reales;
- no asumir acceso de la cuenta a Futures;
- no predeclarar umbral de entrada hasta auditar datos/costos;
- no adaptar la metodología para rescatar resultados de 04B.
