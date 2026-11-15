# Karpathy LLM Wiki 方法的邊界

本 skill 採用「來源可搜尋 → 候選卡片 → 主題索引 → 反向連結」的低成本導航思想，保留以下邊界：

1. 卡片是檢索入口，不是把完整逐字稿壓成不可追溯的摘要。
2. 重要原則要保留多來源、時間戳與 evidence level，才能回到上下文查核。
3. graph／index 是 derived output；canonical transcript、source chunks、manifest 與影片永遠是事實來源。
4. 先使用 Markdown、hash 與 deterministic compiler；只有出現明確檢索瓶頸才引入向量或圖資料庫。
5. 針對缺口建立 coverage queue，而不是靜默丟棄低頻但可能重要的概念。
