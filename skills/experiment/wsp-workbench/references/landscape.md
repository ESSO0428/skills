# 地形與可達性（workflow D）

問題：WSP 回答「目標點是否存在、長什麼樣」；誤差曲面分析回答「從現在的權重，訓練走得到嗎、卡在哪」。實作在 [wsp_landscape.py](../scripts/wsp_landscape.py)。論文見 [evidence.md](./evidence.md) 的地形診斷表。

## L3：只量測，不更新

L3 允許梯度與 Hessian-vector product（HVP），但只能由受信任的 `wsp_landscape` 函式使用：

- 必須明確 `WeightSession(model, policy, access_level="L3", grad_budget=N)`；L1 / L2 呼叫 `local_geometry` 會丟 `AccessDenied`。
- 每次呼叫先扣預算（超過丟 `BudgetExhausted`，且不會開始計算）。
- 函式在 `session.scratch()` 內執行，結束時比對所有參數 hash，不同就丟 `AssertionError`。
- agent 寫的程式仍受 `check_agent_code` 限制，不能用 autograd。
- 結果帶 `level: "L3"`，不與 L1 / L2 的結果混算。

## 工具與讀法

**`landscape_path(session, state_a, state_b, loss_fn, batches, n_points=21)`**（L2）：沿 `(1-t)a + t b` 的損失。`barrier = max_t [L(t) - ((1-t)L(0) + t L(1))]`（Frankle et al.）。`monotone` 表示損失沿路徑從不上升（或從不下降）。花費 `n_points × len(batches)` 次 forward，預算不足就在開始前拒絕；結束後還原權重並驗證 hash。
- barrier 接近 0：兩點在直線上相連；有明顯 barrier：它們在不同盆地。典型例子：同一網路置換隱藏單元後功能相同，但直線中點損失很高。
- `state_a`、`state_b` 必須同架構。若兩者只差單元排列，barrier 不代表它們功能不同。

**`landscape_slice(session, loss_fn, batches, n_points, seed)`**（L2）：在目前點沿一條隨機方向切一刀。方向做 filter normalisation（Li et al.）：每個 filter（權重的一個 row）縮放到該 filter 的範數；偏差等 1-D 參數方向為 0。座標是相對尺度，不是絕對距離。

**`local_geometry(session, loss_fn, batches, iters=20)`**（L3）：
- 梯度範數 `‖∇L‖`。
- 先做 5 次冪迭代估譜半徑 ρ，再對 `H + 1.5ρ I` 做冪迭代得 `λ_max`；對 `λ_max I − H` 做冪迭代得 `λ_min`。每次 HVP 用二階反向傳播，`H v = ∇(∇L · v)`。
- 標籤（門檻是參數，屬 heuristic）：`‖∇L‖ > grad_tol` 為 `not_critical`；否則 `λ_min < −eig_tol` 為 `saddle`，其餘為 `minimum_like`。`sharpness = λ_max`。
- 預算：`1 + 5 + 2·iters` 次評估。

**`reachability_report(target_exists, path, geometry)`**：整合三項證據：(a) WSP 存在證據（編輯或構造出的點達到目標並通過 gate：是 / 否 / 未知）；(b) 路徑結果；(c) 目前點的幾何。輸出結構化 verdict 與標為 heuristic 的建議：
- 目標找不到：懷疑容量不足或上游缺資訊。
- 有 barrier：從編輯後的點出發，或改優化器 / normalisation。
- 梯度大且損失平坦：降低學習率或用 adaptive optimiser。
- 鞍點：動量或小 batch 的雜訊。
- 無 barrier：有一條合理路徑，但**不是保證**。
`barrier_tol` 是以損失為單位的絕對門檻，須依你的損失尺度設定。

## 限制

- 一維或二維切片可能誤導：高維曲面的形狀不等於切片；一定要用 filter normalisation，並多換幾個 seed。
- 冪迭代只給近似值：特徵值接近時收斂慢；`λ_min` 的符號不確定就加大 `iters` 再量一次。
- 訓練損失低不等於泛化好；曲率與 barrier 都是在指定的 batches 上量的。
- HVP 的成本約為一次反向傳播，大模型要先評估預算；L3 不適合在大模型上無上限使用。
- 直線路徑沒有 barrier 不代表優化器會走那條路；有 barrier 也不代表所有路徑都被擋住（Garipov et al. 的曲線可能連通）。

## Checkpoint 軌跡（`checkpoint_trajectory`）

輸入：依時間排序的 state dict（至少 2 個）。對每一段與每個符合 `pattern` 的浮點 tensor 回報：
- `‖ΔW‖_F` 與相對範數 `‖ΔW‖ / ‖W_start‖`；
- 對 ≥2 維 tensor（reshape 成 `(out, -1)`）：ΔW 前 `top_k` 個奇異值的能量占比 `Σσ_i² / Σσ²`（rank-1 的 ΔW 為 1.0）；
- 相鄰兩段（需要 ≥3 個 checkpoint）：攤平 ΔW 的 cosine，以及主子空間重疊 `‖U_aᵀU_b‖_F² / k`（`k` 取兩者數值秩的較小者，奇異值低於最大值 1e-6 倍視為 0）；
- 第一個到最後一個的淨摘要，含 `net_over_path_length`（淨位移除以各段位移長度和，1.0 表示各段位移同向）。

給 session、`loss_fn`、`batches` 時（L2）另做分段路徑：對每對相鄰 checkpoint 跑一次 `landscape_path`，預算 `(段數) × n_points × len(batches)` 先檢查再執行。

**能說與不能說**：
- 能說「這兩個 checkpoint 之間的淨位移集中在哪些 tensor、是否低秩、相鄰兩段的位移是否同向」。
- 不能說「訓練沿著這個方向走」：兩個 checkpoint 之間的實際路徑沒有被觀察到，位移可能是許多來回步驟的淨結果。cosine 與子空間重疊也取決於 checkpoint 的間隔。
- 只有 2 個 checkpoint 時只有一段，方向一致性需要至少 3 個。

**建議**：在使用者自己的訓練迴圈（WSP session 之外）每 N 個 step 存一次 `state_dict`，包含訓練初期與損失變化最大的區段，間隔不必相等但要記錄 step。

