---
name: "Quant Indicators Calculation"
description: "Calculates technical analysis indicators (VWAP, Bollinger Bands, EMA) programmatically using Pandas."
---
# Quant Indicators Calculation Skill

This skill governs programmatic calculation of market metrics using Pandas, eliminating LLM arithmetic hallucinations.

## Key Calculations
1. **VWAP (Volume Weighted Average Price)**:
   $$\text{VWAP} = \frac{\sum (\text{Price} \times \text{Volume})}{\sum \text{Volume}}$$
2. **Bollinger Bands**:
   $$\text{Middle Band} = \text{SMA}(N)$$
   $$\text{Upper Band} = \text{Middle Band} + k \times \sigma$$
   $$\text{Lower Band} = \text{Middle Band} - k \times \sigma$$
3. **Pivot Points**:
   $$P = \frac{H + L + C}{3}, \quad R_1 = 2P - L, \quad S_1 = 2P - H$$
