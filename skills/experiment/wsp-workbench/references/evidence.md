# 證據與出處

「Weight-space programming（WSP）」是 2026 年才出現的概念名稱，**不是已確立的研究領域**。本 skill 的可靠骨幹是 A 級證據：同儕審查的權重編輯方法。B 級是單一模型的初步報告，C 級是未驗證的延伸，只能當假設。

## A 級：同儕審查的方法（驗證過的骨幹）

| 論文 | 重點 | 本 skill 對應 |
|---|---|---|
| Santurkar et al., "Editing a classifier by rewriting its prediction rules", NeurIPS 2021。[連結](https://proceedings.neurips.cc/paper/2021/hash/c46489a2d5a9a9ecfc53b17610926ddd-Abstract.html) | 編輯分類器的單一層，讓某個概念的表徵映射到另一個概念；只需少量範例，無關類別大致不受影響 | `rank_one_key_value`（閉式最小平方版） |
| Belrose et al., "LEACE: Perfect linear concept erasure in closed form", NeurIPS 2023。[連結](https://proceedings.neurips.cc/paper_files/paper/2023/hash/d066d21c619d0a78c5b557fa3291a8f4-Abstract.html) | 閉式解；抹除後任何線性分類器都無法還原該概念；改動最小 | `leace_fit`、`fold_eraser_into_next_linear` |
| Meng et al., "Locating and Editing Factual Associations in GPT"（ROME），NeurIPS 2022。[連結](https://proceedings.nips.cc/paper_files/paper/2022/file/6f1d43d5a82a37e89b0665b33bf3a182-Paper-Conference.pdf) | 用因果追蹤定位，再做 rank-one 編輯；以 efficacy / generalisation / specificity 評估 | `localize_by_patching`、`rank_one_key_value`、`edit_report` |
| Arditi et al., "Refusal in Language Models Is Mediated by a Single Direction", NeurIPS 2024。[連結](https://arxiv.org/abs/2406.11717) | 權重正交化 `W' = W - r rᵀ W`，作用於寫入 residual stream 的矩陣 | `orthogonalize`（等同下方 MIT 報告的 Qwen 編輯） |
| Ilharco et al., "Editing Models with Task Arithmetic", ICLR 2023。[連結](https://arxiv.org/abs/2212.04089) | task vector = finetuned - pretrained；取負或相加可調整行為 | `task_vector`、`apply_task_vector` |

這些論文的實驗多在 LLM 或大型視覺模型上；本 skill 的實作是簡化的閉式版本，差異與限制見 [methods.md](./methods.md)。**不得把本 skill 的結果歸功於論文**。

## B 級：MIT WSP 報告（初步、單一模型）

來源：MIT CSAIL blog 報告，2026-11-02，單一模型 GPT-6 Astra，多為單次嘗試，未經同儕審查。

- **從原始權重文字辨認小網路任務**：4 個 grid-game PPO MLP（17,253 權重）全部答對；3 個 diffusion MLP（23,824 權重）形狀對，但畫成輪廓而非填滿的形狀。
- **用 Python、不執行網路**：char-level transformer（7.16M）答對訓練語言並指出 copying heads。
- **一次回覆修復失敗的 Kinetix 控制策略**（171,664 權重，無工具）：改 3.5% 權重，成功率 0/256 到 1,024/1,024。
- **從零寫網路**：MinAtar 600→32→32→6、Go 9x9（1.48M 權重）；各處勝過 PPO-100M，在 Seaquest 與 Asterix 低於 PPO-500M。
- **Qwen3.5-0.8B**：移除 layer 15 與 19 的 MLP down-projection 所寫入的一個方向（各 64 columns，共 131,072 權重，0.016%），預算 50 次 forward：MATH-500 7.9% 到 48.1%，主要靠消除推理迴圈（撞 token 上限 93% 到 33%）。獨立重跑 51.0%。這與 Arditi 的正交化是同一種運算。
- **作者自述的失敗**：僅憑權重無法分辨 sycophantic 與 honest 的 Gemma 270M（需要 attention 工具）；編輯無法替 Gemma 270M 增加能力（MATH-500 6.8% 到 7.7%）。

獨立驗證：Petcu 的 EMNIST CNN（108,271 參數）以 row cosine 找出易混淆的輸出列（5 個 seed 中 4 個）；對單一輸出列做閉式 rank-1 編輯（35 個權重）修好 E 與 V，沒有其他類別掉分；在 L 與 1 上失敗，因為所需資訊在上游就不存在。同一比較中 fine-tuning 平均準確率較好，但對易混淆類別有附帶傷害。

## C 級：未驗證的延伸（只能當假設）

- 僅憑權重解讀大型網路（目前最大的原始文字案例約 172k 權重）。
- 「讀權重」等於追蹤機制：arXiv 2611.08070（Claude Opus 5.5，CIFAR-10 等的 CNN）發現模型使用資料集先驗加局部算術；輸出標籤被置換、或權重在各 tensor 內被打亂後，模型仍回答「CIFAR-10」。因此每個解讀結論都需要對照。
- 編輯新增能力、backdoor 稽核、unlearning、model merging、self-improvement。
- 能否轉移到其他 LLM；本 skill 跑在 Claude 上，而唯一直接的 Claude 研究結果大多為負面。

## 本 skill 的自我驗證

- `tests/test_end_to_end.py`：合成 5 類資料，植入「部分 class 0 被標成 class 1」，以閉式 rank-1 編輯修復。
- `tests/test_methods.py`：合成 4 類資料，植入「背景維度與 class 0 相關」的捷徑，以 LEACE 折進下一層修復，並檢查 specificity。

這些只證明工具鏈與閉式公式運作，不證明方法在真實模型上有效。
