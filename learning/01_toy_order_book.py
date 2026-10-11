# Toy order book: just two lists. No matching yet, only looking.
bids = [(50, 100), (49, 200), (48, 50)]   # (price, quantity) buyers
asks = [(51, 80), (52, 120), (53, 60)]    # (price, quantity) sellers

best_bid = max(price for price, qty in bids)
best_ask = min(price for price, qty in asks)
spread = best_ask - best_bid

print("best bid :", best_bid)
print("best ask :", best_ask)
print("spread   :", spread)
print("can trade?", best_bid >= best_ask)
