# Provenance policy

Wiki 是 derived navigation。任何主張都必須能沿著下列鏈回到原始材料：

```text
principle → candidate → source chunk → timestamp → video ID → URL → transcript type
```

- `EXPLICIT` 只能描述來源直接支持的內容。
- `STRONG_SYNTHESIS` 與 `INFERENCE` 必須保留 scope、limitations 與 uncertainty。
- AGY、影格或投影片觀察只能作 supplemental observation；沒有 canonical transcript 時要標記缺口。
- `READY_PARTIAL`、`ASR_SEGMENT_UNAVAILABLE`、`ASR_FAILED` 或 blocked 狀態要留在 coverage gaps／log。
- Wiki 編譯器只讀 canonical JSON；不由模型自由改寫來源，不刪除原始媒體、逐字稿或 source chunks。
