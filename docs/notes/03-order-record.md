# 03 - Binary Order Record (`struct`)

## What it does
Turns one order into exactly **32 raw bytes** and back, so it can live in shared memory.
Code: `src/chronosmatch/order_record.py`. Format string lives in `config.py`.

## Layout
| Offset | Size | Field | Type |
|---|---|---|---|
| 0 | 8 | order_id | unsigned 64-bit |
| 8 | 8 | timestamp_ns | unsigned 64-bit (entry time, for Week 3 latency) |
| 16 | 8 | price | signed 64-bit, integer ticks |
| 24 | 4 | quantity | unsigned 32-bit |
| 28 | 1 | side | 0 = BUY, 1 = SELL |
| 29 | 3 | padding | zero |

Format string: `"<QQqIB3x"`. `<` = little-endian with no automatic padding, `Q` = u64,
`q` = i64, `I` = u32, `B` = u8, `3x` = three pad bytes.

## Concepts used (to be taught in the struct/bytes lesson)
- Fixed-size records: every order takes the same space, so record N is at `N * 32`.
- Endianness: the byte order of a multi-byte number. We fix little-endian explicitly.
- `pack_into` / `unpack_from`: write/read at an offset inside an existing buffer, without
  creating a separate bytes object for the record.

## Design decisions
See D11 in `docs/decisions.md`.

## Tests (`tests/test_order_record.py`)
Size is 32; round trip both sides with large values; exact byte layout check; packing at an
offset leaves neighbours untouched; corrupt side code rejected; u32 overflow and too-small
buffers raise.

## Gotchas
- `unpack_from` builds a Python `Order` object every time. That is fine for Week 1, but it is
  exactly the kind of object creation Week 3 removes from the matching loop.
