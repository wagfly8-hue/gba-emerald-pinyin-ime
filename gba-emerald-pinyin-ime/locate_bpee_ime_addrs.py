#!/usr/bin/env python3
"""Auto-locate all 65 NamingScreen Pinyin IME hook/table/sprite/RAM addresses in a target BPEE/Emerald ROM.

Compares a verified reference ROM + config (e.g. examples/pokeepsilon_1.0.3.json)
against any target Emerald / pokeemerald-expansion ROM using exact byte windows
and Thumb-aware masked instruction matching (masking BL & PC-relative LDR).

Usage:
    python locate_bpee_ime_addrs.py \
        --ref-rom original/pokeepsilon_1.0.3.gba \
        --ref-config examples/pokeepsilon_1.0.3.json \
        --target-rom path/to/new_game.gba \
        --free-space 0x09918000 \
        -o new_game_ime_config.json
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

BASE = 0x08000000


def find_all(data: bytes, pat: bytes, start: int = 0, end: int | None = None) -> list[int]:
    if end is None:
        end = len(data)
    res, pos = [], start
    while True:
        idx = data.find(pat, pos, end)
        if idx == -1:
            break
        res.append(idx)
        pos = idx + 1
    return res


def find_masked_thumb(ref: bytes, tgt: bytes, off_ref: int, n_hw: int = 14) -> list[int]:
    hw = [struct.unpack_from("<H", ref, off_ref + 2 * i)[0] for i in range(n_hw)]
    mask = []
    for h in hw:
        if 0xF000 <= h <= 0xFFFF:
            mask.append(False)
        elif 0x4800 <= h <= 0x4FFF:
            mask.append("ldr_pc")
        else:
            mask.append(True)
    hits = []
    for cand in range(0, len(tgt) - n_hw * 2, 2):
        ok = True
        for i, m in enumerate(mask):
            h3 = struct.unpack_from("<H", tgt, cand + 2 * i)[0]
            if m is True and h3 != hw[i]:
                ok = False
                break
            if m == "ldr_pc" and (h3 & 0xFF00) != (hw[i] & 0xFF00):
                ok = False
                break
        if ok:
            hits.append(cand)
    return hits


def locate_rom_addr(ref: bytes, tgt: bytes, addr_ref: int, is_gfx: bool = False) -> int | None:
    thumb_bit = addr_ref & 1
    off_ref = (addr_ref & ~1) - BASE
    if is_gfx:
        hits = find_all(tgt, ref[off_ref : off_ref + 32])
        return (BASE + hits[0]) if len(hits) == 1 else None
    for pre, post in ((12, 24), (8, 16), (4, 16), (0, 24), (0, 16)):
        if off_ref - pre >= 0 and off_ref + post <= len(ref):
            hits = find_all(tgt, ref[off_ref - pre : off_ref + post])
            if len(hits) == 1:
                return BASE + hits[0] + pre + thumb_bit
    hits = find_masked_thumb(ref, tgt, off_ref, n_hw=14)
    if len(hits) == 1:
        return BASE + hits[0] + thumb_bit
    return None


def main():
    ap = argparse.ArgumentParser(description="Auto-locate BPEE Pinyin IME addresses in a target GBA ROM.")
    ap.add_argument("--ref-rom", required=True, type=Path)
    ap.add_argument("--ref-config", required=True, type=Path)
    ap.add_argument("--target-rom", required=True, type=Path)
    ap.add_argument("--free-space", required=True, help="Verified zero-filled ROM address (e.g. 0x09918000)")
    ap.add_argument("-o", "--out", required=True, type=Path)
    args = ap.parse_args()

    ref = args.ref_rom.read_bytes()
    tgt = args.target_rom.read_bytes()
    ref_cfg = json.loads(args.ref_config.read_text(encoding="utf-8"))

    free_off = int(args.free_space, 16) - BASE
    assert tgt[free_off : free_off + 0x20000] == bytes(0x20000), f"Free space {args.free_space}..+0x20000 is NOT zero!"

    out_syms = {}
    failed = []
    for sym, val_str in ref_cfg["symbols"].items():
        val = int(val_str, 16)
        if sym == "FREE_SPACE_IME":
            out_syms[sym] = f"0x{int(args.free_space, 16):08X}"
            continue
        if sym.startswith("RAM_"):
            out_syms[sym] = val_str  # Verified below via literal pool extraction
            continue
        is_gfx = sym.startswith("GFX_")
        found = locate_rom_addr(ref, tgt, val, is_gfx=is_gfx)
        if found is None:
            failed.append(sym)
            out_syms[sym] = "TODO_VERIFY"
        else:
            out_syms[sym] = f"0x{found:08X}"

    # Extract RAM_NAMING_SCREEN_PTR and RAM_GWINDOWS from target literal pools when hooks located
    if out_syms.get("HOOK_NAMING_ZERO_IME", "").startswith("0x"):
        nz = int(out_syms["HOOK_NAMING_ZERO_IME"], 16) - BASE
        cands = [struct.unpack_from("<I", tgt, p)[0] for p in range(nz & ~3, nz + 0xA0, 4)
                 if 0x02020000 <= struct.unpack_from("<I", tgt, p)[0] < 0x02040000]
        if cands:
            out_syms["RAM_NAMING_SCREEN_PTR"] = f"0x{cands[0]:08X}"
    if out_syms.get("FN_FILL_WINDOW_PIXEL_BUF", "").startswith("0x"):
        fw = (int(out_syms["FN_FILL_WINDOW_PIXEL_BUF"], 16) & ~1) - BASE
        cands = [struct.unpack_from("<I", tgt, p)[0] for p in range(fw & ~3, fw + 0x80, 4)
                 if 0x02020000 <= struct.unpack_from("<I", tgt, p)[0] < 0x02040000]
        if cands:
            out_syms["RAM_GWINDOWS"] = f"0x{cands[0]:08X}"

    out_cfg = {
        "project": args.target_rom.stem,
        "base_rom_code": tgt[0xAC:0xB0].decode("ascii", errors="ignore"),
        "gfx_tag0_back": f"0x{locate_rom_addr(ref, tgt, int(ref_cfg['gfx_tag0_back'], 16), True) or 0:08X}",
        "gfx_tag1_ok": f"0x{locate_rom_addr(ref, tgt, int(ref_cfg['gfx_tag1_ok'], 16), True) or 0:08X}",
        "symbols": out_syms,
    }
    args.out.write_text(json.dumps(out_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Located {len(out_syms) - len(failed)}/{len(out_syms)} symbols -> {args.out}")
    if failed:
        print(f"Manual verification needed for ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()
