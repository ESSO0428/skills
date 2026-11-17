---
name: wsp-workbench
description: 實驗性的 weight-space programming 工作台：以推理與閉式公式（不訓練）診斷並編輯 PyTorch 模型權重，方法取自同儕審查的權重編輯論文，附 edit gate、ledger、undo 與 forward budget。
disable-model-invocation: true
---

# wsp-workbench

Weight-space programming（WSP）：agent 讀取模型權重、以推理算出編輯量、直接改權重，用來研究行為、診斷特定錯誤與做權重干預。對象是一般 PyTorch 模型（影像分類器、ViT/CNN/MLP、tabular regressor 等），用 regex 對 `named_parameters()` 選 tensor，不假設任何模型家族。

「WSP」是 2026 年的概念名稱，不是已確立的領域。可靠的骨幹是同儕審查的權重編輯方法（ROME、LEACE、Santurkar、Arditi、task arithmetic），本 skill 只實作其閉式變體，差異見 [methods.md](./references/methods.md)，證據分層見 [evidence.md](./references/evidence.md)。實驗性：只在合成資料上驗證過。

## 鐵則：算，不最佳化

編輯量由推理與閉式計算得出。WSP session 內禁止：訓練迴圈、`.backward()`、`torch.autograd.grad`、`torch.optim`、`requires_grad_(True)`。

- 執行 agent 寫的程式前先用 `check_agent_code(source)`；發現上述用法就丟 `ForbiddenCode`。唯一例外是 L3：只有受信任的 `wsp_landscape` 函式可為「量測」算梯度，絕不更新權重。
- 梯度訓練的 baseline（fine-tuning，或產生 task vector 的微調）只能在 session **之外**跑，並標示「gradient baseline」。
- 編輯是訓練的補充：證據顯示能移除障礙、修正有目標的錯誤，沒有顯示能新增缺少的能力。

## Access level（每個結果都要標，不同 level 不混算）

| Level | 可做的事 |
|---|---|
| L0 | 權重以文字給出，沒有工具 |
| L1 | 用程式讀權重（統計、線性代數），**不執行**網路 |
| L2 | L1 加上有上限的 forward pass（hook 取 activation、activation patching）；預算用完 session 就拒絕 |
| L3 | L2 加上梯度與 Hessian-vector product，**只做量測**；須明確 `WeightSession(access_level="L3", grad_budget=N)`，每次量測扣預算並驗證權重 hash 不變 |

`WeightSession` 接受 L1 / L2 / L3。L3 結果標 L3，不與 L1 / L2 混算。

## Workflow

**A. Weight Reading**（[reading.md](./references/reading.md)）：inventory → 結構統計 → 先寫假設與預測 → 必做對照（within-tensor shuffle、permute output labels）→ 報告。同一結論在對照組也出現就推翻。寫「權重支持 X」，不寫「模型做 X」。

**B. Weight Intervention**（[intervention.md](./references/intervention.md)）：先書面固定目標、metric、切分、預算、門檻 → **定位**（`localize_by_patching`、輸出層 row cosine）→ **選 A 級（同儕審查）方法** → 建立編輯 → **gate**（含 norm-matched 隨機對照）→ held-out 只看一次，報 efficacy / generalisation / specificity → **保留或 `undo`**（`assert_baseline()`）。

**C. Weight Programming**（[programming.md](./references/programming.md)）：從 spec 起手、權重全 0；用推理構造；依 spec 做 unit test；與簡單 baseline 比；每版記 hash。

**D. 地形與可達性**（[landscape.md](./references/landscape.md)）：目標點存在嗎（workflow B 的結果：是 / 否 / 未知）→ `landscape_path`（L2，現在到目標的直線有沒有 barrier）→ `local_geometry`（L3，梯度範數、最大與最小 Hessian 特徵值）→ `reachability_report` 給出標為 heuristic 的建議。不宣稱保證可達。

## 症狀到方法

| 症狀 | 方法（[wsp_methods.py](./scripts/wsp_methods.py)） |
|---|---|
| 模型靠捷徑屬性（背景、站點、浮水印），且有該屬性的標籤 | `leace_fit` + `apply_eraser_to_next_linear` |
| 某類樣本的表徵被導向錯誤輸出（類別混淆） | `rank_one_key_value` / `apply_rank_one` |
| 已找到某層不該寫入的一個方向 | `orthogonalize`（`project_out`，alpha=1） |
| 有 base 與 finetuned 權重，想加減某個行為 | `task_vector` + `apply_task_vector`（λ 事先固定） |
| 不知道該改哪一層 | `localize_by_patching` |
| 修好後要驗證 | `edit_report`、`gate`、`sign_test_p` |
| 目標存在但訓練到不了、想知道卡在哪 | `landscape_path`、`local_geometry`、`reachability_report`（[wsp_landscape.py](./scripts/wsp_landscape.py)） |

## 編輯 op 與符號慣例

四個 op，皆經同一個 gate（允許 / 禁止 tensor、單次改動比例上限、只收有限值、禁止整個 tensor 縮放）：

- `project_out(name, u, alpha, cols)`：`W' = W - alpha * u (uᵀ W)`，`u` 在 W 的輸出空間（rows）且會被正規化。**alpha=1 移除該分量，alpha<1 縮小，alpha>1 翻轉。** 其他專案的符號可能相反。
- `add_rank1(name, a, b, scale)`：`W' = W + scale * a bᵀ`。
- `assign(name, flat_index, values)`、`zero_units(name, units, dim)`。

每次編輯寫入 ledger（JSONL，append-only）：edit id、op、tensor、n_changed、前後 hash、note、access level。`undo(edit_id)` 還原；`undo_all()` 後 `assert_baseline()`，hash 必須與起點完全相同。

## Gate 門檻（事前固定，不看結果調整）

practice 上對照同形隨機編輯：`fixed >= max(3, 20% 的 baseline 失敗數)`、`broke <= fixed/4`、`fixed` 大於對照組；另報精確 sign test p。通過後 held-out 只看一次。

## 工具

Windows 原生，只需要 PyTorch（`.safetensors` 另加 `--extra safetensors`）。

**執行工具**：`<root>` 是含 `pyproject.toml` 的 skill 根目錄（即本目錄）。
- 有 `uv.lock`，或 `pyproject.toml` 含 `[project]`：`uv run --project <root> python <腳本>`（首次自動建 `.venv`）。
- 沒有 uv 但有 `<root>/.venv`：直接用 `<root>/.venv/Scripts/python`（Windows）或 `<root>/.venv/bin/python`。
- 都沒有：照 [README](./README.md) 安裝；缺套件就回報安裝指令，不改用其他環境。
- 需要 torch 時第一次先 `uv sync --project <root> --extra cpu`；有 NVIDIA GPU 改用 `cu126`（舊驅動）或 `cu132`（`nvidia-smi` 的 CUDA Version ≥ 13.2）。

| 檔案 | 用途 |
|---|---|
| [scripts/wsp_inspect.py](./scripts/wsp_inspect.py) | CLI：`inventory`、`stats`、`cosine`、`dump`（整數 × 單一 scale，有字元上限） |
| [scripts/wsp_session.py](./scripts/wsp_session.py) | `EditPolicy`、`WeightSession`、`ForwardBudget`、`check_agent_code` |
| [scripts/wsp_methods.py](./scripts/wsp_methods.py) | 閉式方法、定位、`edit_report` |
| [scripts/wsp_landscape.py](./scripts/wsp_landscape.py) | 路徑 barrier、filter-normalised 切片、局部幾何（L3）、可達性報告 |
| [scripts/wsp_controls.py](./scripts/wsp_controls.py) | `matched_random_direction`、`shuffled_copy`、`permute_outputs` |
| [scripts/wsp_compare.py](./scripts/wsp_compare.py) | `paired_counts`、`sign_test_p`、`gate`、`per_class_deltas` |

範例：`uv run --project <root> python <root>/scripts/wsp_inspect.py stats model.pt --pattern "fc|head"`。完整流程見 [test_end_to_end.py](./tests/test_end_to_end.py) 與 [test_methods.py](./tests/test_methods.py)、[test_landscape.py](./tests/test_landscape.py)；跑測試：`uv run --project <root> --extra dev pytest <root>/tests -q -p no:cacheprovider`。載入權重只用 `torch.load(weights_only=True)`。

## 誠實規則

- 每個結論標 access level、模型、樣本數與信心；單次嘗試不當成確定事實。
- 結果不得歸功於論文：本 skill 是閉式簡化版。
- 「讀懂權重」未經對照驗證前一律是假設。不確定時保留 `unknown`；失敗的編輯與無效的對照照實回報。
- 不宣稱優於 fine-tuning；比較時分開列平均表現與副作用。
