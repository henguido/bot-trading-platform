import datetime
from backend.config import settings

class CryptoPosition:
    def __init__(self, quantity=0.0, average_price=0.0, last_movement=None):
        self.quantity = quantity
        self.average_price = average_price
        self.last_movement = last_movement  # ← nuevo campo

class Simulator:
    def __init__(self):
        self.capital_usd = settings.INITIAL_CAPITAL_USD
        self.positions = {}  # ← corregido: ya no usamos settings.ASSETS
        self.history = []
        self.audit_log = []  # Log de contexto de decisiones

    def simulate_trade(self, symbol, action, price, quantity, risk_score=None):
        if symbol not in self.positions:
            self.positions[symbol] = CryptoPosition()

        position = self.positions[symbol]
        position.last_movement = datetime.datetime.now()

        if action == "COMPRAR" and quantity > 0:
            amount_usd = quantity * price

            if amount_usd > self.capital_usd:
                print(f"[⚠️] No hay suficiente capital para comprar {quantity:.6f} de {symbol} a ${price:.2f}")
                return

            new_total_quantity = position.quantity + quantity
            if new_total_quantity > 0:
                position.average_price = (
                    (position.quantity * position.average_price) + (quantity * price)
                ) / new_total_quantity
            position.quantity = new_total_quantity

            self.capital_usd -= amount_usd
            self.history.append(self._create_history_entry(symbol, "COMPRA", price, quantity, risk_score))

            print(f"[{datetime.datetime.now()}] Simulación: COMPRA {quantity:.6f} de {symbol} a ${price:.2f}")

        elif action == "VENDER" and quantity > 0 and position.quantity >= quantity:
            amount_usd = quantity * price
            self.capital_usd += amount_usd

            self.history.append(self._create_history_entry(symbol, "VENTA", price, quantity, risk_score))
            print(f"[{datetime.datetime.now()}] Simulación: VENTA {quantity:.6f} de {symbol} a ${price:.2f}")

            position.quantity -= quantity
            if position.quantity == 0:
                position.average_price = 0.0

        else:
            print(f"[{datetime.datetime.now()}] Simulación: Espera en {symbol}")

    def simulate_swap(self, pair_symbol, from_asset, to_asset, price, quantity_from, risk_score=None):
        if from_asset not in self.positions or self.positions[from_asset].quantity < quantity_from:
            print(f"[⚠️] No hay suficiente {from_asset} para realizar el swap.")
            return

        quantity_to = quantity_from * price

        # Restar del activo origen
        self.positions[from_asset].quantity -= quantity_from
        if self.positions[from_asset].quantity == 0:
            self.positions[from_asset].average_price = 0.0

        # Agregar al activo destino
        if to_asset not in self.positions:
            self.positions[to_asset] = CryptoPosition()

        destino = self.positions[to_asset]
        nuevo_total = destino.quantity + quantity_to
        if nuevo_total > 0:
            destino.average_price = (
                (destino.quantity * destino.average_price) + (quantity_to * price)
            ) / nuevo_total
        destino.quantity = nuevo_total

        self.history.append({
            "symbol": pair_symbol,
            "action": "SWAP",
            "from": from_asset,
            "to": to_asset,
            "price": price,
            "quantity_from": quantity_from,
            "quantity_to": quantity_to,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "risk_score": risk_score
        })

        print(f"[{datetime.datetime.now()}] Simulación: SWAP {quantity_from:.6f} {from_asset} ➝ {quantity_to:.6f} {to_asset} @ {price}")

    def log_decision_context(self, symbol, sentimiento, noticias, decision, quantity, risk_score):
        self.audit_log.append({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "sentimiento": sentimiento,
            "noticias": noticias,
            "decision": decision,
            "quantity": quantity,
            "risk_score": risk_score
        })

    def get_audit_log(self):
        return self.audit_log

    def _create_history_entry(self, symbol, action, price, quantity, risk_score):
        return {
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "risk_score": risk_score
        }

    def show_summary(self, current_prices):
        print("\n------ RESUMEN SIMULADOR ------")
        total_value = self.capital_usd
        for symbol, position in self.positions.items():
            if position.quantity > 0:
                total_value += position.quantity * current_prices.get(symbol, 0)
        print(f"Capital USD disponible: ${self.capital_usd:.2f}")
        print(f"Valor total estimado (USD + cripto): ${total_value:.2f}")

        print("\nPosiciones abiertas:")
        for symbol, position in self.positions.items():
            if position.quantity > 0:
                print(f"  {symbol}: {position.quantity:.6f} @ ${position.average_price:.2f}")

        print("\nHistorial de operaciones:")
        for entry in self.history:
            print(entry)
        print("-------------------------------\n")
