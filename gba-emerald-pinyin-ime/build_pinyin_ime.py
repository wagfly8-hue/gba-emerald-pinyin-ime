#!/usr/bin/env python3
"""Reusable GBA Pokemon (BPEE / Emerald) Chinese Pinyin IME Builder.

Generates:
  1. Offline prefix-searchable Pinyin dictionary (`pinyin_dict.bin`) ranked by
     project text frequency + Pokemon naming favorites.
  2. Crisp 7-8px Chinese NamingScreen button sprites (`pinyin_btn.bin`,
     `btn_upper.bin`, `btn_lower.bin`, `btn_others.bin`, `btn_back.bin`,
     `btn_ok.bin`) preserving original 9px capsules & outline/shadow styles.
  3. Ready-to-assemble `naming_pinyin.asm` rendered from `naming_pinyin.asm.tmpl`
     with all ROM/RAM symbols from `--config` and auto-resolved `拼`/`音`/`退`
     codepoints from `--charmap` (preventing charmap-shift bugs forever).

Usage:
    python build_pinyin_ime.py \
        --rom original/game.gba \
        --charmap font/charmap.json \
        --config ime_config.json \
        --out-dir font \
        --out-asm patch/naming_pinyin.asm \
        [--translated text/translated.json] \
        [--asset-dir font]
"""
from __future__ import annotations

import argparse
import json
import re
import struct
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TMPL = HERE / "naming_pinyin.asm.tmpl"
DEFAULT_WIN_PINYIN = Path(r"C:\Windows\System32\chs_singlechar_pinyin.dat")

MANUAL_PINYIN = {
    "昇": ["sheng"],
}

NAMING_BOOST_ORDER = (
    "小大一二人中天生火水草电风雷冰龙星月日云山海光暗影梦心爱乐美"
    "皮卡丘杰尼龟妙蛙种子火稚鸡木守宫水跃鱼喷射暴鲤伊布拉普达超"
    "力壮焰烈咬陆鲨耿鬼沙奈朵路利欧波加曼裂空固拉多盖基拉祈阿"
    "白黑红蓝绿黄紫金银铁钢玉石花雪雨露霜青翠赤苍绯碧蓝琉璃珀"
    "男女子娃宝可智茂遥真光芽衣透也琴音翔太春树秋夏冬"
)

# Self-contained crisp 9x9 bitmaps based on Fusion Pixel 10px (TakWolf)
# Fits expanded 11px capsule interior with exact 1px top & 1px bottom margin/outline
BTN_GLYPHS_9 = {
    "大": [
        "....#....",
        "....#....",
        "#########",
        "....#....",
        "....#....",
        "...#.#...",
        "...#.#...",
        "..#...#..",
        "##.....##",
    ],
    "小": [
        "....#....",
        "....#....",
        ".#..#..#.",
        ".#..#..#.",
        ".#..#...#",
        "#...#...#",
        "#...#...#",
        "....#....",
        "...##....",
    ],
    "写": [
        "#########",
        "#.#.....#",
        "..######.",
        "..#......",
        "..######.",
        ".......#.",
        "######.#.",
        ".......#.",
        "....###..",
    ],
    "音": [
        "....#....",
        ".#######.",
        "..#...#..",
        "..#...#..",
        "#########",
        ".#.....#.",
        ".#######.",
        ".#.....#.",
        ".#######.",
    ],
    "号": [
        ".#######.",
        ".#.....#.",
        ".#######.",
        ".........",
        "#########",
        "..#......",
        ".#######.",
        ".#.....#.",
        "....###..",
    ],
    "定": [
        "....#....",
        "#########",
        "#.......#",
        ".#######.",
        "....#....",
        "..#.####.",
        "..#.#....",
        ".#.##....",
        "#....####",
    ],
    "拼": [
        ".#...#..#",
        ".#...#.#.",
        "###.#####",
        ".#...#.#.",
        ".#...#.#.",
        ".##.#####",
        "##...#.#.",
        ".#...#.#.",
        "##..#..#.",
    ],
    "符": [
        ".#...#...",
        ".###.####",
        "#.#.#..#.",
        "..#....#.",
        ".#.######",
        "##.....#.",
        ".#.#...#.",
        ".#..#..#.",
        ".#....##.",
    ],
    "退": [
        "#..######",
        ".#.#....#",
        "...######",
        "##.#....#",
        ".#.######",
        ".#.#..#..",
        ".#.##..##",
        "#.#......",
        "#..######",
    ],
    "格": [
        ".#..#....",
        ".#..####.",
        "####...#.",
        ".#..#..#.",
        "###..##..",
        "##.##..##",
        "##..####.",
        ".#..#..#.",
        ".#..####.",
    ],
    "确": [
        "###..#...",
        ".#..####.",
        ".#.#...#.",
        "#...#####",
        "###.#.#.#",
        "#.#.#####",
        "#.#.#.#.#",
        "###.#.#.#",
        "...#...##",
    ],
}


def load_pinyin_map(dat_path: Path) -> dict[str, list[str]]:
    raw = dat_path.read_bytes()
    py_map: dict[str, list[str]] = {}
    for off in range(0, len(raw), 8):
        cp = int.from_bytes(raw[off : off + 2], "little")
        py = raw[off + 2 : off + 8].split(b"\x00", 1)[0].decode("ascii", errors="ignore").lower()
        if not py or not py.isascii():
            continue
        ch = chr(cp)
        lst = py_map.setdefault(ch, [])
        if py not in lst:
            lst.append(py)
    for ch, pys in MANUAL_PINYIN.items():
        py_map[ch] = list(pys)
    return py_map


def compute_char_freq(translated_path: Path | None) -> Counter[str]:
    freq: Counter[str] = Counter()
    if translated_path and translated_path.exists():
        data = json.loads(translated_path.read_text(encoding="utf-8"))
        for entry in data.get("strings", []):
            txt = entry.get("text") or ""
            for ch in txt:
                if "\u4e00" <= ch <= "\u9fff":
                    freq[ch] += 1
    n_boost = len(NAMING_BOOST_ORDER)
    for idx, ch in enumerate(NAMING_BOOST_ORDER):
        freq[ch] += (n_boost - idx) * 200
    return freq


def build_dict(charmap_path: Path, out_dict: Path, translated_path: Path | None, pinyin_dat: Path) -> dict[str, str]:
    cm = json.loads(charmap_path.read_text(encoding="utf-8"))
    double_2b: dict[str, str] = cm["double_2b"]
    py_map = load_pinyin_map(pinyin_dat)
    freq = compute_char_freq(translated_path)

    by_syllable: dict[str, list[tuple[str, bytes]]] = {}
    missing = []
    for ch, hex_code in double_2b.items():
        if not ("\u4e00" <= ch <= "\u9fff"):
            continue
        code_bytes = bytes.fromhex(hex_code)
        pys = py_map.get(ch)
        if not pys:
            missing.append(ch)
            continue
        for py in pys:
            by_syllable.setdefault(py, []).append((ch, code_bytes))

    assert not missing, f"Missing pinyin for Hanzi (add to MANUAL_PINYIN): {missing}"
    syllables = sorted(by_syllable.keys())

    index_entries = bytearray()
    char_pool = bytearray()
    cur_char_idx = 0
    for sy in syllables:
        items = by_syllable[sy]
        items.sort(key=lambda x: (-freq[x[0]], ord(x[0])))
        sy_bytes = sy.encode("ascii")
        assert len(sy_bytes) <= 7
        index_entries.extend(sy_bytes.ljust(8, b"\x00"))
        index_entries.extend(struct.pack("<HH", cur_char_idx, len(items)))
        for _, code_bytes in items:
            char_pool.extend(code_bytes)
        cur_char_idx += len(items)

    header = struct.pack("<HHI", len(syllables), 0, cur_char_idx)
    blob = header + index_entries + char_pool
    while len(blob) % 4 != 0:
        blob += b"\x00"
    out_dict.write_bytes(blob)
    print(f"[IME] Built {out_dict.name}: {len(syllables)} syllables, {cur_char_idx} entries, {len(blob)} B")
    return double_2b


def _glyph_grid(ch: str) -> list[list[int]]:
    return [[1 if c == "#" else 0 for c in r] for r in BTN_GLYPHS_9[ch]]


def _decode_4bpp_tiles(rom: bytes, rom_addr: int, w_tiles: int, h_tiles: int) -> list[list[int]]:
    off = rom_addr - 0x08000000
    grid = [[0] * (w_tiles * 8) for _ in range(h_tiles * 8)]
    for ty in range(h_tiles):
        for tx in range(w_tiles):
            t = ty * w_tiles + tx
            for y in range(8):
                for x in range(4):
                    b = rom[off + t * 32 + y * 4 + x]
                    grid[ty * 8 + y][tx * 8 + x * 2] = b & 0xF
                    grid[ty * 8 + y][tx * 8 + x * 2 + 1] = b >> 4
    return grid


def _encode_4bpp_tiles(grid: list[list[int]], w_tiles: int, h_tiles: int) -> bytes:
    out = bytearray(w_tiles * h_tiles * 32)
    for ty in range(h_tiles):
        for tx in range(w_tiles):
            t = ty * w_tiles + tx
            for y in range(8):
                for x in range(8):
                    c = grid[ty * 8 + y][tx * 8 + x]
                    off = t * 32 + y * 4 + (x >> 1)
                    if x & 1:
                        out[off] = (out[off] & 0x0F) | ((c & 0xF) << 4)
                    else:
                        out[off] = (out[off] & 0xF0) | (c & 0xF)
    return bytes(out)


def _render_32x16_pill_label(text: str, fg: int, shadow: int) -> bytes:
    """Crisp 9px Chinese label inside expanded 11px capsule (y=2..12) with 3-way drop shadow."""
    canvas = [[0] * 32 for _ in range(16)]
    glyphs = [_glyph_grid(ch) for ch in text]
    gap = 2
    tot_w = sum(len(g[0]) for g in glyphs) + gap * (len(glyphs) - 1)
    cur_x = 2 + (27 - (tot_w + 1)) // 2
    fg_pts = set()
    for g in glyphs:
        y0 = 3 + (9 - len(g)) // 2
        for dy, r in enumerate(g):
            for dx, v in enumerate(r):
                if v:
                    fg_pts.add((cur_x + dx, y0 + dy))
        cur_x += len(g[0]) + gap

    for px, py in fg_pts:
        for dx, dy in ((1, 0), (0, 1), (1, 1)):
            sx, sy = px + dx, py + dy
            if 2 <= sx <= 28 and 2 <= sy <= 12 and (sx, sy) not in fg_pts:
                canvas[sy][sx] = shadow
    for px, py in fg_pts:
        if 2 <= px <= 28 and 2 <= py <= 12:
            canvas[py][px] = fg
    return _encode_4bpp_tiles(canvas, 4, 2)


def _patch_40x32_top_box(orig_rom: bytes, box_addr: int) -> bytes:
    """Expand top SELECT button capsule cutout from 9px (y=7..15) to 11px (y=6..16)."""
    orig = _decode_4bpp_tiles(orig_rom, box_addr, 5, 4)
    grid = [[0] * 40 for _ in range(32)]
    # Top frame shifted up 1px: orig rows 3..7 -> rows 2..6
    for y in range(3, 8):
        grid[y - 1] = list(orig[y])
    # Middle cutout rows 7..15 (uniform inner cutout from orig row 8)
    for y in range(7, 16):
        grid[y] = list(orig[8])
    # Bottom cutout corner + bottom frame + SELECT shifted down 1px: orig rows 15..27 -> rows 16..28
    for y in range(15, 28):
        grid[y + 1] = list(orig[y])
    return _encode_4bpp_tiles(grid, 5, 4)


def _patch_32x16_top_pill(orig_rom: bytes, pill_addr: int) -> bytes:
    """Expand top SELECT button pill fill from 9px (y=4..12) to 11px (y=3..13)."""
    orig = _decode_4bpp_tiles(orig_rom, pill_addr, 4, 2)
    grid = [[0] * 32 for _ in range(16)]
    grid[3] = list(orig[4])
    for y in range(4, 13):
        grid[y] = list(orig[5])
    grid[13] = list(orig[12])
    return _encode_4bpp_tiles(grid, 4, 2)


def _patch_40x24_yellow_pill(orig_rom: bytes, rom_addr: int, is_back: bool, text: str) -> bytes:
    """Expand BACK/OK yellow capsule to 11px and render crisp 9px Chinese text with 8-neighbor gold outline."""
    orig = _decode_4bpp_tiles(orig_rom, rom_addr, 5, 3)
    grid = [list(r) for r in orig]
    if is_back:
        # Expand BACK capsule from 4..12 (9px) to 3..13 (11px), keeping row 0 border and rows 16..23 B BUTTON
        grid[1] = list(orig[2])   # dark border E
        grid[2] = list(orig[3])   # white border 1
        grid[3] = list(orig[4])   # rounded top yellow interior
        for y in range(4, 13):
            grid[y] = list(orig[5])
        grid[13] = list(orig[12]) # rounded bottom yellow interior
        grid[14] = list(orig[13]) # white border 1
        grid[15] = list(orig[14]) # dark border E
        pill_y0, pill_y1 = 3, 13
    else:
        # Expand OK capsule from 2..10 (9px) to 2..12 (11px), shifting bottom border & START> down into row 23
        grid[0] = list(orig[0])   # dark border E
        grid[1] = list(orig[1])   # white border 1
        grid[2] = list(orig[2])   # rounded top yellow interior
        for y in range(3, 12):
            grid[y] = list(orig[3])
        grid[12] = list(orig[10]) # rounded bottom yellow interior
        grid[13] = list(orig[11]) # white border 1
        grid[14] = list(orig[12]) # dark border E
        for y in range(14, 23):
            grid[y + 1] = list(orig[y]) # START> (15..21), padding (22), bottom border F (23)
        pill_y0, pill_y1 = 2, 12

    for y in range(pill_y0, pill_y1 + 1):
        for x in range(7, 33):
            if grid[y][x] in (1, 12, 13):
                grid[y][x] = 13

    glyphs = [_glyph_grid(ch) for ch in text]
    gap = 2
    tot_w = sum(len(g[0]) for g in glyphs) + gap * (len(glyphs) - 1)
    cur_x = 7 + (26 - tot_w) // 2
    fg_pts = set()
    for g in glyphs:
        y0 = pill_y0 + 1 + (9 - len(g)) // 2
        for dy, r in enumerate(g):
            for dx, v in enumerate(r):
                if v:
                    fg_pts.add((cur_x + dx, y0 + dy))
        cur_x += len(g[0]) + gap

    for px, py in fg_pts:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                sx, sy = px + dx, py + dy
                if 6 <= sx <= 33 and pill_y0 <= sy <= pill_y1 and (sx, sy) not in fg_pts and grid[sy][sx] == 13:
                    grid[sy][sx] = 12
    for px, py in fg_pts:
        if 7 <= px <= 32 and pill_y0 <= py <= pill_y1:
            grid[py][px] = 1
    return _encode_4bpp_tiles(grid, 5, 3)


def build_button_sprites(orig_rom: bytes, back_addr: int, ok_addr: int, box_addr: int, pill_addr: int, out_dir: Path):
    (out_dir / "pinyin_btn.bin").write_bytes(_render_32x16_pill_label("拼音", fg=1, shadow=6))
    (out_dir / "btn_upper.bin").write_bytes(_render_32x16_pill_label("大写", fg=1, shadow=6))
    (out_dir / "btn_lower.bin").write_bytes(_render_32x16_pill_label("小写", fg=1, shadow=8))
    (out_dir / "btn_others.bin").write_bytes(_render_32x16_pill_label("符号", fg=1, shadow=10))
    (out_dir / "btn_box.bin").write_bytes(_patch_40x32_top_box(orig_rom, box_addr))
    (out_dir / "btn_pill.bin").write_bytes(_patch_32x16_top_pill(orig_rom, pill_addr))
    (out_dir / "btn_back.bin").write_bytes(_patch_40x24_yellow_pill(orig_rom, back_addr, True, "退格"))
    (out_dir / "btn_ok.bin").write_bytes(_patch_40x24_yellow_pill(orig_rom, ok_addr, False, "确定"))
    print(f"[IME] Built 8 NamingScreen button sprites in {out_dir}")


def _hex_bytes_csv(double_2b: dict[str, str], text: str) -> str:
    parts = []
    for ch in text:
        assert ch in double_2b, f"Required IME UI character {ch!r} missing from charmap.json!"
        raw = bytes.fromhex(double_2b[ch])
        parts.extend(f"0x{b:02X}" for b in raw)
    return ", ".join(parts)


def render_asm(tmpl_path: Path, cfg: dict, double_2b: dict[str, str], asset_dir: str, out_asm: Path):
    tmpl = tmpl_path.read_text(encoding="utf-8")
    subs = dict(cfg["symbols"])
    subs["ASSET_DIR"] = asset_dir.replace("\\", "/").rstrip("/")
    subs["BYTES_PINYIN"] = _hex_bytes_csv(double_2b, "拼音")
    subs["BYTES_DEL"] = _hex_bytes_csv(double_2b, "退")

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in subs:
            raise KeyError(f"Missing symbol {key!r} in IME config")
        return subs[key]

    rendered = re.sub(r"\{([A-Z0-9_]+)\}", _sub, tmpl)
    out_asm.parent.mkdir(parents=True, exist_ok=True)
    out_asm.write_text(rendered, encoding="utf-8")
    print(f"[IME] Generated {out_asm} (拼音={subs['BYTES_PINYIN']}, 退={subs['BYTES_DEL']})")


def main():
    ap = argparse.ArgumentParser(description="Build reusable GBA Pokemon Chinese Pinyin IME assets & ASM.")
    ap.add_argument("--rom", required=True, type=Path, help="Clean base GBA ROM (.gba)")
    ap.add_argument("--charmap", required=True, type=Path, help="Project charmap.json (with double_2b)")
    ap.add_argument("--config", required=True, type=Path, help="IME address config JSON (from locate_bpee_ime_addrs.py)")
    ap.add_argument("--out-dir", required=True, type=Path, help="Output directory for pinyin_dict.bin & btn_*.bin")
    ap.add_argument("--out-asm", type=Path, help="Output path for generated naming_pinyin.asm")
    ap.add_argument("--asset-dir", default="font", help="Relative .incbin directory inside generated ASM (default: font)")
    ap.add_argument("--translated", type=Path, help="Optional translated.json for candidate frequency ranking")
    ap.add_argument("--pinyin-dat", type=Path, default=DEFAULT_WIN_PINYIN, help="Path to chs_singlechar_pinyin.dat")
    ap.add_argument("--template", type=Path, default=DEFAULT_TMPL, help="Path to naming_pinyin.asm.tmpl")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    double_2b = build_dict(args.charmap, args.out_dir / "pinyin_dict.bin", args.translated, args.pinyin_dat)
    orig_rom = args.rom.read_bytes()
    build_button_sprites(
        orig_rom,
        int(cfg["gfx_tag0_back"], 16),
        int(cfg["gfx_tag1_ok"], 16),
        int(cfg["symbols"]["GFX_TAG2_BOX"], 16),
        int(cfg["symbols"]["GFX_TAG3_PILL"], 16),
        args.out_dir,
    )
    if args.out_asm:
        render_asm(args.template, cfg, double_2b, args.asset_dir, args.out_asm)


if __name__ == "__main__":
    main()
