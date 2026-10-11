# 00 - Big Picture: What is ChronosMatch?

## The problem in one paragraph
A stock exchange is a place where people post offers to buy and sell. Trading firms
send thousands of these offers per second. Something has to take each offer, find a
matching opposite offer, and record a trade, fast and in the right order.
ChronosMatch is a small, learning-grade version of that "something" (a *matching engine*),
built so that data moves between programs without being copied or converted.

## Who would use it
A quantitative analyst or trading engineer who wants to see orders flow in, get matched,
and measure how long each step takes (in microseconds).

## The three ideas
1. **Shared memory (mmap):** two separate programs read and write the same bytes in RAM.
2. **Ring buffer:** a fixed-size circular queue inside that shared memory.
3. **Cython matching engine:** the order-matching loop compiled to C speed, using C types.

## Data flow

    +-------------------+        +----------------------------+        +--------------------+
    | Market Simulator  |        |   Shared memory (mmap)     |        |  Matching Engine   |
    | (asyncio, Python) | writes |  RING BUFFER of fixed-size | reads  |  (Cython, C types) |
    | makes fake orders | -----> |  order records (raw bytes) | -----> |  Limit Order Book  |
    +-------------------+        +----------------------------+        +---------+----------+
                                                                                 |
                                                       trades + timestamps       v
                                   +--------------------+              +--------------------+
                                   | Latency Monitor    | <----------- | Trades output      |
                                   | (curses dashboard) |              | (later: SQLite)    |
                                   +--------------------+              +--------------------+

## Four modules
| Module | Job | Week |
|---|---|---|
| IPC ring buffer | Move order bytes between processes with no pickle/JSON | 1 |
| Market simulator | Blast mock orders into the buffer (target 100k/sec) | 1 |
| Matching engine | Limit order book, price-time priority, in Cython | 2 |
| Dashboard | Show best bid/ask, spread, latency | 2 (+3, 4) |

## Honest limitation
Python/Cython cannot match C++/FPGA systems used in real HFT. This is a learning-grade
engine that demonstrates the *techniques*.
