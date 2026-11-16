# Workflow C：Weight Programming（從 spec 寫權重）

1. **Spec**：寫下輸入輸出的編碼、架構與預期行為；所有權重從 0 開始（`torch.zeros`）。
2. **構造**：用推理決定每一層的權重。程式只用來建矩陣（例如 one-hot 路由、閾值單元、查表），**不用資料擬合**，也不跑訓練。
3. **Unit test**：依 spec 寫測試，輸入空間小時窮舉。
4. **評估**：與簡單 baseline（規則程式或小模型）比較；結果標 access level。
5. **版本紀錄**：每個版本以 `tensor_hash` 記錄各 tensor 的 hash（或透過 `WeightSession` 的 ledger 寫入）。

限制：已知的成功案例（MinAtar、Go 9x9）來自單一模型的單一報告，見 [evidence.md](./evidence.md)；不要把它當成對任意 spec 都可行。
