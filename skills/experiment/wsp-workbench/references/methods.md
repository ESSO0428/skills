# 方法：何時用、公式、與論文的差異

實作在 [wsp_methods.py](../scripts/wsp_methods.py)，全部經 `WeightSession` 的 gate（allowlist、改動上限、有限值、ledger）。沒有任何梯度。論文出處見 [evidence.md](./evidence.md)。

**通則**：這裡實作的是「閉式最小平方」變體。下列論文的原始流程有些部分用最佳化，本 skill 沒有實作，所以結果**不能歸功於論文**。

## 1. Rank-one key/value 編輯（ROME、Santurkar 的啟發）

- **何時用**：某一層的輸入特徵（key）應該改映射到另一個輸出（value），例如分類器最後一層要把某類樣本的 hidden 表徵導向正確類別 logits。
- **公式**：`W' = W + (v - W k)(C⁻¹k)ᵀ / ((C⁻¹k)ᵀ k)`。保證 `W' k = v`，並在 key 共變異數 `C` 加權下改動最小（`C` 省略時為單位矩陣）。`k`、`C` 來自 L2 forward（hook 取該層輸入）。
- **差異**：
  - ROME 的 value `v` 是用梯度最佳化求得，`C` 來自大量文字的統計；本實作 `v` 要由你用推理給出（例如目標 logits），沒有最佳化。
  - Santurkar 的原始流程用限制式最佳化微調一層；本實作只有單一 key 的閉式更新。
  - 兩篇都有大量實驗驗證 specificity；這裡必須用 `edit_report` 自己驗證。

## 2. LEACE 線性概念抹除（Belrose et al.）

- **何時用**：模型靠捷徑（背景、浮水印、站點、批次、性別等屬性）預測；你有該屬性的標籤（可以是 practice 資料上的屬性，不需要是預測目標）。
- **公式**：`r(x) = x - W⁺ P W (x - μ)`，`W = Σxx^(-1/2)`（特徵分解，特徵值下限為最大值的 1e-8 倍），`P` 是 `W Σxz` 欄空間的正交投影。抹除後，r(x) 的任何線性函數與 Z 都不相關。折進下一個線性層：`W_next' = W_next (I - W⁺PW)`、`b' = b + W_next W⁺PW μ`，所以不需要改前向程式。
- **差異**：論文有多種擴充與理論保證的細節；這裡是基本閉式版，以 float64 計算。只保證**線性**抹除，非線性的下游層仍可能從別的路徑還原概念；保證只對擬合資料成立。
- **注意**：practice 資料中概念必須與你要保留的標籤盡量獨立，否則抹除會連帶抹掉有用訊號。

## 3. 權重正交化（Arditi et al.）

- **何時用**：已找到寫入某個空間的一個方向 `r`（例如以類別平均差得出），想讓這一層不再寫入該方向。
- **公式**：`W' = W - r rᵀ W`，`r` 為單位向量、屬於 W 的輸出空間（rows）。這是 `project_out(alpha=1)`；alpha<1 縮小、alpha>1 翻轉。
- **差異**：論文針對 LLM 中寫入 residual stream 的所有矩陣，方向由對比資料的平均差取得；這裡一次只改你指定的 tensor，方向由你決定。

## 4. Task arithmetic（Ilharco et al.）

- **何時用**：你有同一架構、同一個初始化的 base 與 finetuned 權重（微調在 session 之外完成，標為 gradient baseline 的產物），想要用 `base + λ τ` 調整或抵消某個行為。
- **公式**：`τ = finetuned - base`；套用 `W' = W + λ τ`，λ<0 為取負。
- **差異**：論文在 CLIP 等大模型上系統性掃描 λ 並以驗證集選擇；本 skill 要求 λ 事先固定（候選清單）。λ=0 不是編輯，gate 會拒絕。注意 task vector 的來源包含梯度訓練，使用時必須標示。

## 5. 定位：activation patching（ROME 因果追蹤的分類器類比）

- **何時用**：不知道該改哪一層時，先看哪一層的 activation 對目標行為有因果作用。
- **做法**：`localize_by_patching(session, layers, x_clean, x_corrupt, metric_fn)`：把 clean 輸入的各層輸出逐一貼到 corrupt 輸入的前向中，效果 = 貼上後的 metric 減去 corrupt 的 metric。花費 `2 + 層數` 次 forward（算進預算）。
- **差異**：ROME 的因果追蹤是在 token 位置與層的網格上，並加雜訊破壞主詞；這裡只做每層整體貼上，且要求 clean 與 corrupt 為成對樣本。貼上整層輸出時，其後各層的效果會被一併計入，所以離輸出越近的層效果越大，要與你的假設一起判讀。

## 6. 評估：efficacy / generalisation / specificity

`edit_report(base_preds, new_preds, labels, target_mask, used_mask)`：
- efficacy：用來建構編輯的目標樣本（`used_mask`）上的變化。
- generalisation：其餘沒用到的目標樣本。
- specificity：所有非目標樣本，附每類前後變化。
編輯後的 held-out 只看一次。

## 選法

見 [SKILL.md](../SKILL.md) 的「症狀到方法」表。
