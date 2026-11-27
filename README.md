# GBA Pokémon Emerald (BPEE) Chinese Pinyin IME

一个自包含、可复用的 **GBA 宝可梦绿宝石（`BPEE` / `pokeemerald-expansion`）离线中文拼音输入法模块**，基于 ARMIPS 汇编补丁实现，无第三方 Python 依赖。

## 核心特性

- **原生 4 页命名键盘循环**：`拼音（默认） → 小写 → 符号 → 大写 → 拼音`，按 `SELECT` 或 `R`（拼音缓冲为空时）切换。
- **离线前缀检索词库（`pinyin_dict.bin`）**：约 400 个拼音音节，支持结合项目译文词频 + 宝可梦/训练家高频起名汉字排序；`L`/`R` 键翻页（每页 6 个候选汉字）。
- **零硬编码 EWRAM 冲突**：自动扩展 `sNamingScreen` 分配空间 `0x1F30 → 0x1F80`（+`0x50` 字节）并在进入命名界面时清零初始化。
- **完整的双字节汉字编辑与变宽光标**：
  - 在 `maxChars` 限制内安全插入双字节汉字（`0x87..0x9F`）。
  - `B` / `退` 优先退格拼音字母，缓冲区为空时完整删除一个双字节汉字，不会残留半字乱码。
  - 变宽名称渲染（汉字 +12px / 拉丁字符 +8px），下划线精灵自动对齐并在双字节第二字节隐藏。
  - 光标默认停在 `(0, 1)` `'a'`，方向键跳过空候选行，候选栏内自动限位，选字后自动回弹。
- **原版风格中文胶囊按钮**：保留绿宝石右侧 `退格` / `确定` / 页面切换胶囊样式，内置 9×9 点阵字形（基于 Fusion Pixel 10px 风格），无需额外字体文件。
- **防码表漂移（Charmap-Shift Proof）**：构建时自动从项目 `charmap.json` 解析 `拼`、`音`、`退` 的双字节码位，避免换码表导致乱码。
- **跨改版自动定位地址**：提供 `locate_bpee_ime_addrs.py`，可通过字节窗口与 Thumb 掩码匹配自动定位目标 `BPEE` / `pokeemerald-expansion` ROM 中的 65 个 Hook / 表 / 精灵 / RAM 地址。

## 目录结构

```text
gba-emerald-pinyin-ime/
├── build_pinyin_ime.py          # 生成离线拼音词库、8 个中文按钮精灵和 naming_pinyin.asm
├── locate_bpee_ime_addrs.py     # 自动定位目标 BPEE ROM 的 65 个符号地址
├── naming_pinyin.asm.tmpl       # ARMIPS 汇编补丁模板
├── examples/
│   └── pokeepsilon_1.0.3.json   # 参考配置示例（Pokemon Epsilon v1.0.3, BPEE）
├── docs/
│   └── pinyin-ime.md            # 技术细节与快速参考
├── LICENSE
└── README.md
```

## 环境要求

- **Python 3.10+**（仅使用标准库，无需 `pip install`）
- **ARMIPS**（用于将生成的 `naming_pinyin.asm` 汇编注入 GBA ROM）
- **拼音码表文件**：默认使用 Windows 系统自带的 `C:\Windows\System32\chs_singlechar_pinyin.dat`；在 Linux/macOS 下可通过 `--pinyin-dat` 参数指定同类 8 字节定长单字拼音表文件。
- **前置条件**：目标 ROM 需已接入双字节中文字库渲染（如 `0x87..0x9F` 编码区），并具备包含 `double_2b` 映射的 `charmap.json`。

## 快速上手

### 第 1 步：自动定位目标 ROM 地址

使用已验证的参考 ROM 与参考配置，为你的目标绿宝石（`BPEE`）改版生成 `ime_config.json`：

```bash
python locate_bpee_ime_addrs.py \
    --ref-rom original/ref_emerald.gba \
    --ref-config examples/pokeepsilon_1.0.3.json \
    --target-rom original/target_game.gba \
    --free-space 0x09918000 \
    -o patch/ime_config.json
```

> 说明：`--free-space` 需指向目标 ROM 中至少 `0x20000` 字节连续全零（`0x00`）的空闲区域。如果输出中包含 `TODO_VERIFY` 项（说明目标改版修改过 NamingScreen C 代码），请反汇编核对对应地址（尤其是 `HandleDpadCursor` 中的寄存器分配）。

### 第 2 步：构建词库、按钮精灵与汇编补丁

```bash
python build_pinyin_ime.py \
    --rom original/target_game.gba \
    --charmap font/charmap.json \
    --config patch/ime_config.json \
    --translated text/translated.json \
    --out-dir font \
    --out-asm patch/naming_pinyin.asm \
    --asset-dir font
```

- `--translated` 为可选项：传入项目译文 JSON 后，会自动统计字频以优化候选字排序。
- 生成产物包括 `pinyin_dict.bin`、8 个 `btn_*.bin` / `pinyin_btn.bin` 按钮贴图，以及可直接汇编的 `naming_pinyin.asm`。

### 第 3 步：集成到主 ARMIPS 补丁

在你的主字体/汉化补丁脚本（例如 `patch_font.asm`）的 `.close` 之前加入一行：

```asm
.include "patch/naming_pinyin.asm"
```

使用 `armips` 汇编后，在模拟器（如 mGBA）中进入起名界面验证以下场景：
1. 默认进入 **拼音** 页，按 `SELECT` / `R` 顺畅循环 4 个页面。
2. 输入多字中文名（如 `皮卡丘`），测试 `L` / `R` 翻页选字。
3. 按 `B` 依次退格拼音字母和已输入的双字节汉字。
4. 确认命名后检查对话文本中的主角/宝可梦名称显示正常。

## 适用范围

- 仅支持 **宝可梦绿宝石（`BPEE`）及 `pokeemerald-expansion` 衍生改版**。
- **不直接支持**火红（`BPRE`）或红蓝宝石（`AXVE` / `AXPE`），因命名界面结构体与 UI 布局不同。
<img width="240" height="160" alt="image" src="https://github.com/user-attachments/assets/9055afa1-fab5-47ea-90e7-3d36fce156fe" />
<img width="240" height="160" alt="image" src="https://github.com/user-attachments/assets/8c5bacfc-848c-4156-b15b-e8d9a44d9b83" />
<img width="240" height="160" alt="image" src="https://github.com/user-attachments/assets/0749403e-f51a-49be-bea3-b1ee615f383d" />
<img width="240" height="160" alt="image" src="https://github.com/user-attachments/assets/bc536139-c8e0-4cf4-8e9c-842d981cd682" />




## 声明

本仓库仅包含原创输入法工具脚本、汇编模板与开源配置示例，**不包含任何任天堂/Game Freak 版权 ROM 文件或专有游戏资源**。

## License

[MIT](LICENSE)
