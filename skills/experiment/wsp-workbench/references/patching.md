# Activation patching：多輸入、多節點與交互作用

L2 的主要證據來源，尤其是輸出不是類別的模型（embedding、回歸值）：靜態讀權重（L1）只能提出假設，patching 才量到「哪個節點對輸出有因果作用」。實作在 [wsp_methods.py](../scripts/wsp_methods.py) 與 [wsp_controls.py](../scripts/wsp_controls.py)。

## 多輸入模型

`session.forward(*args, capture=None, patch=None, **kwargs)` 接受任意位置與關鍵字輸入，輸入會搬到權重所在的裝置；一次呼叫扣一次預算。需要把輸入打包時，用 `session.forward_inputs(inputs)`：`inputs` 可以是單一 tensor、tuple / list（位置參數）或 dict（關鍵字參數）。`localize_by_patching` 與 `patch_plan` 都吃這種 `inputs`。不需要自己寫 wrapper。

## 補丁模式（`make_patch(mode, activation, seed)`）

| mode | 做法 | 檢驗的問題 |
|---|---|---|
| `zero` | 換成 0 | 拿掉訊號：輸出還需要這個節點嗎 |
| `mean` | 換成 batch 平均，廣播到每個樣本 | 拿掉樣本特有的資訊但保留平均：需要的是樣本差異，還是平均偏移 |
| `resample` | 換成同 batch 另一個樣本的 activation（seed 決定的排列，沒有任何樣本留在原位；batch 為 1 時無法重抽，原樣回傳） | 保留分佈、打斷配對：輸出是否依賴這個樣本自己的內容 |
| tensor | 使用你給的 tensor | 自訂（例如另一個資料集的 activation） |

`zero` 可能把 activation 推到分佈之外，傷害會被放大；`mean` 與 `resample` 較溫和。三種結果不一致時，三種都報告，不挑一個。

## `patch_plan(session, nodes, inputs, metric_fn, mode, seed, max_order)`

`metric_fn(output, inputs) -> float`，越高越好（accuracy、cosine、retrieval 都行）。流程：baseline → 每個單節點 → 每一對 →（超過 2 個節點時）全部一起。預算先檢查：`1 + n + C(n,2)`，n > 2 時再加 1；不足就在花任何一次 forward 之前丟 `BudgetExhausted`。`max_order=1` 只做單節點。所有補丁共用同一個 seed，所以 `resample` 在每個節點換掉的是同一批樣本。

每列回傳 `{nodes, metric, delta, order}`，`delta = metric(patched) - metric(baseline)`，負數表示傷害。對雙節點與全部一起的列另有：

```
interaction = delta_joint - sum(單節點 delta)
```

符號慣例（`tests/test_patching.py` 固定它）：
- `interaction ≈ 0`：效果可加。
- `interaction < 0`：一起拿掉傷害**大於**單獨傷害的總和。節點互為備援，單獨拿掉其中一個會被另一個遮住（例如 head 取 max，兩個分支訊號相同）。
- `interaction > 0`：一起拿掉傷害**小於**總和。節點共同決定同一個效果，任何一個拿掉就已經損失了，傷害不會疊加（例如 head 取乘積）。

這是「在這個 metric、這批資料、這個補丁模式」下的交互作用，不是架構上的定論。

## 稠密輸出的對照組

- `shuffle_pairing(inputs, which, seed)`：把其中一個輸入在 batch 內打亂（沒有樣本留在原位），打斷與其他輸入的配對；若模型真的用到配對，metric 會掉。
- `random_activation(activation, seed)`：每個樣本以相同範數的隨機向量取代。
- `permute_outputs` 只適用於類別輸出（置換類別標籤）；embedding 或回歸輸出請改用上面兩個。

## 範例 (a)：兩個輸入的模型，用 tuple 或 dict 呼叫

```python
class TwoInput(torch.nn.Module):          # forward(x1, x2)
    ...
sess = WeightSession(model, policy, access_level="L2", budget=12)
out = sess.forward(x1, x2)                                  # 直接傳多個位置參數
out = sess.forward_inputs((x1, x2))                         # tuple / list：位置參數
out = sess.forward_inputs({"x1": x1, "x2": x2})             # dict：關鍵字參數
out, acts = sess.forward(x1, x2, capture=["branch_a"])      # capture 與 patch 一樣可用
```

輸入在 CPU、權重在 GPU 也可以，session 會搬。

## 範例 (b)：兩個輸入的回歸模型，cosine 評估

模型有兩個分支 `a`、`b`，各吃一個輸入向量，輸出一個 embedding；目標是預測 embedding 與參考向量的 cosine。

```python
sess = WeightSession(model, EditPolicy(allowed=["head"]), access_level="L2", budget=12)
cos = lambda out, inputs: torch.nn.functional.cosine_similarity(out, ref).mean().item()
plan = patch_plan(sess, ["branch_a", "branch_b"], (x_a, x_b), cos, mode="zero")   # 4 次 forward
plan_r = patch_plan(sess, ["branch_a", "branch_b"], (x_a, x_b), cos, mode="resample")  # 再 4 次
```

讀法：
1. 每個單節點的 `delta`：誰的貢獻較大。
2. 雙節點列的 `interaction`：可加、備援還是共同決定。
3. `resample` 比 `zero` 傷害更大，代表輸出依賴的是這個樣本自己的內容，而不只是有沒有訊號。
4. 再用 `shuffle_pairing` 對輸入 B 做對照：metric 掉多少，就是模型對配對的依賴。

單次、單一資料集的結果標 L2 與樣本數，不推廣成對所有輸入都成立。

## 範例 (c)：retrieval metric（recall@k）

輸出是 embedding、要用「在 gallery 裡找得到同一個身分」評估時，用 [wsp_compare.py](../scripts/wsp_compare.py) 的 `recall_at_k`：預測 embedding 與 gallery 做 cosine，前 k 名裡有任何一個標籤與 query 相同就算命中。

```python
from wsp_compare import recall_at_k

# gallery_emb: (G, d) 參考 embedding；gallery_ids: (G,) 身分；query_ids: (Q,) 每個 query 的身分
# self_idx: (Q,) 每個 query 自己在 gallery 裡的位置（沒有就 -1）
def metric_fn(out, inputs):
    return recall_at_k(out, gallery_emb, query_ids, gallery_ids, k=5, exclude_self=self_idx)

plan = patch_plan(sess, ["branch_a", "branch_b"], (x_a, x_b), metric_fn, mode="zero")
```

注意事項：
- query 與 gallery 要依身分分組切分：同一個身分的 query 不能拿自己（或與自己幾乎相同的樣本）去對 gallery，否則 recall 被灌水。`exclude_self` 會把 query 自己對應的 gallery 項目排除；若排除後該身分在 gallery 裡沒有其他正例，這個 query 會被略過（全部略過回傳 nan）。
- `inputs` 是這次呼叫的輸入，`shuffle_pairing` 對照時 query 與標籤的對應也要一併打亂或重算，否則 metric 量到的是標籤錯位，不是模型的依賴。
- 結果標 k、gallery 大小與 query 數。
