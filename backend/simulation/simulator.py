# simulation/simulator.py

import datetime
from config import settings

class CryptoPosition:
    def __init__(self):
        self.quantity = 0.0
        self.average_price = 0.0

class Simulator:
    def __init__(self):
        self.capital_usd = settings.INITIAL_CAPITAL_USD
        self.positions = {crypto: CryptoPosition() for crypto in settings.CRYPTO_LIST}
        self.history = []

    def simulate_trade(self, symbol, action, price):
        position = self.positions[symbol]

        if action == "COMPRAR" and self.capital_usd > 10:
            amount_usd = self.capital_usd * settings.RISK_PER_TRADE
            amount_crypto = amount_usd / price

            # Update position
            new_total_quantity = position.quantity + amount_crypto
            if new_total_quantity > 0:
                position.average_price = ((position.quantity * position.average_price) + (amount_crypto * price)) / new_total_quantity
            position.quantity = new_total_quantity

            self.capital_usd -= amount_usd
            self.history.append(self._create_history_entry(symbol, "COMPRA", price, amount_crypto))

            print(f"[{datetime.datetime.now()}] Simulación: COMPRA {amount_crypto:.6f} de {symbol} a ${price:.2f}")

        elif action == "VENDER" and position.quantity > 0:
            amount_usd = position.quantity * price
            self.capital_usd += amount_usd

            self.history.append(self._create_history_entry(symbol, "VENTA", price, position.quantity))
            print(f"[{datetime.datetime.now()}] Simulación: VENTA {position.quantity:.6f} de {symbol} a ${price:.2f}")

            position.quantity = 0.0
            position.average_price = 0.0

        else:
            print(f"[{datetime.datetime.now()}] Simulación: Espera en {symbol}")

    def _create_history_entry(self, symbol, action, price, quantity):
        return {
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
