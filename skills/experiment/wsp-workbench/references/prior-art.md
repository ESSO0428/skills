# 既有專案與取捨

本 skill 的程式全部重寫，沒有複製以下任何專案的程式碼。

## 論文（方法的來源；只借數學想法，實作差異見 [methods.md](./methods.md)）

| 論文 | 借鏡的想法 | 沒有採用的部分 |
|---|---|---|
| Santurkar et al. 2021（改寫分類器的預測規則） | 以少量範例改單一層，檢查無關類別 | 限制式最佳化微調 |
| Belrose et al. 2023（LEACE） | 閉式線性概念抹除，可折進下一層 | 論文中的其他變體與理論細節 |
| Meng et al. 2022（ROME） | 先定位再 rank-one 編輯；efficacy / generalisation / specificity | 梯度求 value、文字統計的 key 共變異數、token 網格因果追蹤 |
| Arditi et al. 2024（單一方向的拒絕） | 權重正交化 `W - r rᵀ W` | 跨所有 residual 寫入矩陣的流程與對比資料取向 |
| Ilharco et al. 2023（task arithmetic） | task vector 加減 | 以驗證集掃描 λ |

## 專案

| 專案 | 授權 | 借鏡的想法 | 不採用的部分 |
|---|---|---|---|
| OpenWiSH | MIT OR Apache-2.0 | 硬性 edit gate（允許 / 禁止 tensor、改動比例上限、只收有限值、禁止整個 tensor 縮放）、小 op 集、append-only ledger 與前後 hash、access level 標示、kernel 拒絕 backward 與 optimiser | Linux 限定（Rust + bubblewrap），本 skill 要 Windows 原生 |
| di37 skill | MIT | 固定候選清單加 norm-matched 隨機對照、門檻先於結果、成對 fixed / broke 與 sign test、held-out 只看一次、用 regex 選 tensor | Qwen 專用 preset；只有 denylist 的寫入防護 |
| Oumi weights-lab | Apache-2.0 | 以 edit id undo、「還原後必須等於 baseline」不變式、具名評估與 diff、forward 計數 | 允許梯度，依報告的規則不算 WSP |
| heydtn skill | 無授權 | 只借想法：以 forward 預算分級（0 / 1–2 / 10–50） | 不複製任何程式碼 |

符號慣例差異：di37 的 `project_out` 與本 skill 相同（`W' = W - alpha * u (uᵀ W)`，alpha=1 移除分量）；heydtn 的符號相反，兩者的 alpha 不可互換。本 skill 以 `tests/test_units.py` 固定此慣例。
