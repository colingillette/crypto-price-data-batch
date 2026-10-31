# crypto-price-data-batch
A simple python script that periodically collects crypto order book data from Polymarket and other sources. Used to collect data for later research and training.

## Run Locally

1. Install Python 3
2. PIP Install Imports used in Polymarketv1.py
3. Run with `python Polymarktv1.py`

This will write a new file in the snapshots folder for each 15 minute market. Every five seconds, it will poll 
Polymarket for its current order books and prices.