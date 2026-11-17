# wsp-workbench

> [!WARNING]
> 實驗性 skill，不保證穩定。目前只在合成資料的小型分類器上驗證過；用在真實模型時，所有結論先當假設。

讓 agent 以推理與閉式公式（不訓練、不用梯度）讀取、診斷並編輯 PyTorch 模型的權重：找出類別混淆或捷徑特徵、做秩一編輯或概念抹除，並驗證效果與副作用。適用一般深度學習模型（影像分類器、ViT/CNN/MLP、tabular regressor 等），不綁特定架構。

- 方法取自同儕審查的權重編輯論文（ROME、LEACE、Santurkar 等、Arditi 等、task arithmetic）的閉式變體，證據分級見 [`references/evidence.md`](./references/evidence.md)。
- 每次編輯都經過 edit gate（允許哪些 tensor、改動比例上限、只收有限值）、寫入 ledger，並可 `undo` 回到逐位元相同的原始權重。
- 另有誤差曲面診斷（workflow D）：目標點存在後，量測從目前權重到它的路徑 barrier 與局部曲率，判斷訓練卡在哪；梯度與 Hessian 只在明確開啟的 L3 用於量測，絕不更新權重。
- 只能明確呼叫（`/wsp-workbench`），agent 不會自行觸發。

## 透過 skills.sh 安裝

裝在單一專案（建議，只在要用的 AI 專案裡出現）：

```bash
cd <你的專案>
npx skills add ESSO0428/skills -s wsp-workbench
```

或全域安裝，在 `add` 後面加 `-g`。CLI 會詢問要裝給哪個 agent。

已經裝過舊版的話：

```bash
npx skills update wsp-workbench -y        # 全域安裝加 -g
```

## 建立 uv 環境（第一次）

安裝只會複製檔案。不帶參數的 `uv sync` 或第一次 `uv run` 會從 PyPI 裝 torch：Linux 上是用 CUDA 13 編譯的版本，需要較新的驅動；Windows 上是 CPU 版。先看 `nvidia-smi` 右上角的 CUDA Version，再決定第一次用哪個指令：

| 機器 | 指令 |
|---|---|
| CUDA Version ≥ 13.2 | Linux 不用指定；Windows 用 `uv sync --project <skill 目錄> --extra cu132` |
| CUDA Version 12.x（例如 12.4） | `uv sync --project <skill 目錄> --extra cu126` |
| 沒有 NVIDIA 顯示卡，想要較小的安裝 | `uv sync --project <skill 目錄> --extra cpu` |

`<skill 目錄>`：專案安裝在 `<你的專案>/.agents/skills/wsp-workbench`，全域安裝在 `~/.agents/skills/wsp-workbench`。要讀 `.safetensors` 再加 `--extra safetensors`。

之後一律用 `uv run --project <skill 目錄> python <腳本>`，**不要**再帶 `--extra cpu` 之類的參數，否則 uv 會把已裝的 GPU 版換掉。

確認環境（約 15 秒）。有 GPU 卻出現 `skipped` 與「NVIDIA driver ... too old」警告，代表 torch 版本比驅動新，改用上表的 `cu126`：

```bash
uv run --project <skill 目錄> --extra dev pytest <skill 目錄>/tests -q -p no:cacheprovider
```

## 和你的模型一起用

| 要做的事 | 用哪個環境 |
|---|---|
| 只讀存好的權重檔（`wsp_inspect.py inventory/stats/cosine`） | skill 自己的環境 |
| 載入模型、跑 forward、做編輯（需要 import 你的模型類別） | 你專案的環境，把 `<skill 目錄>/scripts` 加進 `PYTHONPATH` |

第二種情況 skill 的工具只依賴 PyTorch，你的專案環境本來就有，不會衝突。

## 目錄

- `SKILL.md` — 工作流程、存取等級（L0/L1/L2/L3）、症狀對應方法、誠實規則
- `references/` — 證據分級、讀取 / 介入 / 編程流程、方法公式與和論文的差異、相關實作比較
- `scripts/` — `wsp_inspect.py`（CLI）、`wsp_session.py`、`wsp_methods.py`、`wsp_landscape.py`（誤差曲面診斷）、`wsp_controls.py`、`wsp_compare.py`
- `tests/` — 單元測試與植入錯誤的端到端測試（不連網，CPU 可跑）
