"""Toy matching: price-time priority and partial fills.

Resting asks (sellers) in the order they arrived:
    id=1  sell 50 @ 51
    id=2  sell 30 @ 51   (same price, arrived later)
    id=3  sell 40 @ 52
A buyer then arrives: buy 100 @ 52.
"""

# (order_id, price, quantity); the list order IS the arrival order (time).
asks = [(1, 51, 50), (2, 51, 30), (3, 52, 40)]

buy_id, buy_price, buy_qty = 99, 52, 100

# Price priority first (lowest ask first); time priority breaks ties.
# sorted() is stable, so equal prices keep their arrival order.
asks = sorted(asks, key=lambda o: o[1])

trades = []
remaining = buy_qty
book = []
for order_id, price, qty in asks:
    if remaining > 0 and price <= buy_price:
        fill = min(remaining, qty)
        trades.append((buy_id, order_id, price, fill))
        remaining -= fill
        if qty > fill:
            book.append((order_id, price, qty - fill))   # partially filled seller stays
    else:
        book.append((order_id, price, qty))

for buyer, seller, price, qty in trades:
    print(f"TRADE buyer={buyer} seller={seller} price={price} qty={qty}")
print("buyer unfilled qty :", remaining)
print("asks left in book  :", book)
