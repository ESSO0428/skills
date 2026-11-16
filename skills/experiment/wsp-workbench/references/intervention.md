# Workflow B：Weight Intervention

範例實作：[tests/test_end_to_end.py](../tests/test_end_to_end.py)（rank-one 修復錯誤標籤造成的混淆）與 [tests/test_methods.py](../tests/test_methods.py)（LEACE 修復捷徑特徵）。方法細節見 [methods.md](./methods.md)。

1. **先書面固定**：目標行為、metric、practice / held-out 切分、forward 預算、gate 門檻與候選編輯清單（例如固定的 scale 或 λ 列表）。看結果後不得改。
2. **Baseline 與定位**：在 practice 上跑一次，找出錯誤集中的類別 / slice；用 `localize_by_patching` 或輸出層 row cosine 決定要改哪一層。
3. **選方法**：依 SKILL.md 的「症狀到方法」表選一個 A 級方法，只用四個 op（`project_out`、`add_rank1`、`assign`、`zero_units`）經 edit gate 套用。編輯量是閉式計算，不是擬合。
4. **ledger**：每次套用都有 edit id、op、tensor、n_changed、前後 hash、note、level。
5. **Practice 評估**：每個候選都對照同形、norm-matched 的隨機編輯（`matched_random_direction`，或 LEACE 用打亂的概念標籤）；用 `paired_counts` 與 `gate`：`fixed >= max(3, 20% baseline 失敗數)`、`broke <= fixed/4`、`fixed` 大於對照 fixed，並報精確 sign test p。每個候選評估完先 `undo`，再 `assert_baseline()`。
6. **Held-out 只看一次**：用 `edit_report` 報 efficacy、generalisation、specificity（含每類前後變化）；副作用超過事先設定的容忍度就視為失敗。
7. **保留或還原**：失敗就 `undo_all()` 後 `assert_baseline()`，照實回報，不調門檻補救。

注意事項：

- 隨機對照可能有不小的效果（編輯本身會移動輸出），所以 gate 要求勝過對照，而不是只看 fixed。
- `max_fraction_changed` 是單次編輯相對該 tensor 的比例；輸出層或折進下一層的編輯幾乎整個 tensor 都會變，需要設得夠大，但仍要寫在事前政策裡。
- 移除捷徑會同時拿掉模型靠捷徑答對的樣本（例如背景正好吻合的 class 0），這是真實代價，要在 specificity 外另外報告。
- 若資訊在上游表徵就不存在（Petcu 的 L 與 1 案例），編輯修不好，這種結果要如實記錄。
