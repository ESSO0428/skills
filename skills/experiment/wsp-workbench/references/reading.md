# Workflow A：Weight Reading

目標：說明權重「支持」什麼結構或任務。報告寫「權重支持 X」，不寫「模型做 X」。

1. **Inventory**：`uv run python scripts/wsp_inspect.py inventory model.pt`，得到名稱、shape、dtype、數量與每個 tensor 的 sha256。
2. **結構統計**：`stats` 看範數、奇異值譜、effective rank、近零與 dead 單元；`cosine --pattern <輸出層>` 看輸出層 row 兩兩相似度（易混淆類別的候選）。大 tensor 用 `dump --max-chars` 取有限的整數文字，不全量貼入。
3. **先寫信念檔**：任何 probe 之前，寫下假設與可證偽的預測（檔案存在才能事後對照）。
4. **必做對照**：
   - `shuffled_copy`：每個 tensor 內打亂值，保留值的多重集合。
   - `permute_outputs`：置換輸出單元。
   同一個結論若在對照組也成立，結論作廢。這是因為解讀可能只來自資料集先驗與命名，而非權重結構。
5. **選用 L2 probe**：在 `ForwardBudget` 內，以 hook 取 activation；用完即停。
6. **報告**：標 access level、信心與對照結果；未通過對照的結論列為 `unknown`。

提醒：L0 / L1 沒有執行網路的證據，不能說「模型會做 X」。
