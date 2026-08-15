#!/usr/bin/env python3
"""Static arithmetic checks for Linux v5.10 compressed startup_32 early page tables."""

PAGE = 4096
ENTRY = 8
L2_SIZE = 2 * 1024 * 1024
ENTRIES_PER_TABLE = PAGE // ENTRY
L2_TABLES = 4
LEAVES = ENTRIES_PER_TABLE * L2_TABLES
BOOT_INIT_PGT_SIZE = 6 * PAGE
FLAGS = 0x183


def decode_flags(value: int) -> dict[str, int]:
    return {
        "P": (value >> 0) & 1,
        "RW": (value >> 1) & 1,
        "US": (value >> 2) & 1,
        "PS": (value >> 7) & 1,
        "G": (value >> 8) & 1,
    }


def walk_identity(linear: int) -> tuple[int, int, int, int]:
    if not 0 <= linear < 4 * 1024**3:
        raise ValueError("address must be in [0, 4 GiB)")
    l3_index = (linear >> 30) & 0x1ff
    l2_index = (linear >> 21) & 0x1ff
    offset = linear & (L2_SIZE - 1)
    leaf_number = l3_index * ENTRIES_PER_TABLE + l2_index
    physical_base = leaf_number * L2_SIZE
    return l3_index, l2_index, offset, physical_base + offset


def main() -> None:
    assert BOOT_INIT_PGT_SIZE == 24 * 1024
    assert ENTRIES_PER_TABLE == 512
    assert LEAVES == 2048
    assert LEAVES * L2_SIZE == 4 * 1024**3
    assert decode_flags(FLAGS) == {"P": 1, "RW": 1, "US": 0, "PS": 1, "G": 1}

    print(f"pgtable_bytes={BOOT_INIT_PGT_SIZE} pages={BOOT_INIT_PGT_SIZE // PAGE}")
    print(f"layout=L4@+0x0000 L3@+0x1000 L2@+0x2000..+0x5fff")
    print(f"entries_per_table={ENTRIES_PER_TABLE} l2_tables={L2_TABLES} leaves={LEAVES}")
    print(f"coverage=0x{LEAVES * L2_SIZE:x} bytes")
    print("flags_0x183=" + ",".join(f"{k}={v}" for k, v in decode_flags(FLAGS).items()))

    # L3 entries point to four consecutive L2 pages relative to the pgtable base.
    l3_targets = [0x2000 + i * PAGE for i in range(4)]
    assert l3_targets == [0x2000, 0x3000, 0x4000, 0x5000]
    print("l3_targets=" + ",".join(f"+0x{x:04x}" for x in l3_targets))

    samples = [0x0, 0x1fffff, 0x200000, 0x12345678, 0x40000000, 0xffe00000, 0xffffffff]
    for linear in samples:
        l3, l2, off, physical = walk_identity(linear)
        assert physical == linear
        print(
            f"linear=0x{linear:08x} l3={l3} l2={l2} "
            f"offset=0x{off:05x} physical=0x{physical:08x}"
        )


if __name__ == "__main__":
    main()
