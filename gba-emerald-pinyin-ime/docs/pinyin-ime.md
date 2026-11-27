# Reusable GBA Pokémon (BPEE / Emerald) Chinese Pinyin IME Module

Location: `assets/pinyin_ime/`

A self-contained, battle-tested **Solution A (Page 3)** offline Chinese Pinyin IME for Pokémon Emerald (`BPEE`) and `pokeemerald-expansion` ROM hacks, extracted and generalized from Pokémon Epsilon v1.0.3.

## Features Included Out of the Box

- **Integrated 4-Page NamingScreen Cycle**: `拼音 (default) → 小写 → 符号 → 大写 → 拼音` via `SELECT` or `R` (when Pinyin buffer is empty).
- **Offline Prefix-Searchable Pinyin Dictionary** (`pinyin_dict.bin`): ~400 syllables, ranked by project corpus frequency + popular Pokémon/Trainer naming characters, `L`/`R` candidate paging (6 Hanzi/page).
- **Zero Hardcoded EWRAM**: Expands `sNamingScreen` allocation `0x1F30 → 0x1F80` (+`0x50` bytes) and zero-initializes on entry.
- **Full 2-Byte Hanzi Editing & Variable-Width Cursor**:
  - Inserts 2-byte Chinese characters (`0x87..0x9F`) safely within `maxChars`.
  - `B` / `退` pops Pinyin letters first, then deletes full 2-byte Hanzi cleanly without leaving orphan bytes.
  - Variable-width name rendering (+12px Hanzi / +8px Latin) with accurate underline sprite positioning & hiding on 2nd byte.
  - Cursor starts on `(0, 1)` `'a'`, skips empty Row 0 on D-pad, wraps cleanly inside valid candidates `col = 3..2+nCand`, sits at `y=87` (1px above divider line), and snaps back to `(0, 1)` after selecting a Hanzi.
- **Original 9px Right-Hand Capsule Style**: Preserves the exact original Emerald `BACK`/`OK`/Page-Swap 9px capsules, 8-neighbor gold outline on `退格`/`确定`, and 3-way drop shadow on `小写`/`大写`/`符号`/`拼音` using built-in crisp 7–8px bitmaps (zero external font file dependency).
- **Charmap-Shift Proof**: `build_pinyin_ime.py` auto-resolves `拼`, `音`, and `退` byte codes directly from the project's `charmap.json` whenever generating `naming_pinyin.asm`.

## Quick Start for Any New BPEE / Emerald Project

### Step 1: Auto-locate ROM/RAM Addresses
```bash
python assets/pinyin_ime/locate_bpee_ime_addrs.py \
    --ref-rom <verified_ref_rom.gba> \
    --ref-config assets/pinyin_ime/examples/pokeepsilon_1.0.3.json \
    --target-rom original/target_game.gba \
    --free-space 0x09918000 \
    -o patch/ime_config.json
```
Verify any `TODO_VERIFY` entries (if the target hack modified NamingScreen C code) by inspecting disassembly, especially `HandleDpadCursor` register assignments (`r6 = &col`, `r5 = &row`).

### Step 2: Build IME Assets & Generate `naming_pinyin.asm`
```bash
python assets/pinyin_ime/build_pinyin_ime.py \
    --rom original/target_game.gba \
    --charmap font/charmap.json \
    --config patch/ime_config.json \
    --translated text/translated.json \
    --out-dir font \
    --out-asm patch/naming_pinyin.asm \
    --asset-dir font
```

### Step 3: Include in Your Master ARMIPS Patch
Add one line before `.close` in your project's `patch_font.asm`:
```asm
.include "patch/naming_pinyin.asm"
```
Assemble with `armips.exe` and verify in an emulator (init on Pinyin page, cycle all 4 pages, type multi-char Chinese name e.g. `皮卡丘`, test `L`/`R` paging, `B` delete letter & Hanzi, and confirm dialogue).
