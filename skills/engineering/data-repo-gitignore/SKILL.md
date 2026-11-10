---
name: data-repo-gitignore
description: 為資料型 / ML repo 規劃與驗證 `.gitignore`：資料類目錄各自宣告保留清單、root 全域副檔名排除，並用 `git check-ignore` 實測。
disable-model-invocation: true
---

# 資料型 repo 的 .gitignore 策略

兩層防線：**資料類目錄各自宣告自己保留什麼**（per-directory `.gitignore`），**root 用副檔名全域攔截大檔**（不管檔案被放到哪裡）。最後用 `git check-ignore` 實測，結果不靠推理。

## 1. 盤點（決定哪些目錄是資料類）

列出 repo 頂層目錄與大小（`du -sh */`），把目錄分成兩類：

- **資料類**：原始輸入、衍生 dataset、模型輸出、報表、外部專案、靜態大檔、raw data symlink 所在處。→ 寫 per-directory `.gitignore`。
- **程式類**：`src/`、`tests/`、`configs/`、`experiments/` 等。→ 只受 root 副檔名規則保護。

同時記下每個資料類目錄「要進 git 的東西」：`README.md`、取檔腳本（`*.sh`）、要公開的子目錄說明等。

完成條件：每個頂層目錄都歸類，且資料類目錄都有一份「保留清單」。

## 2. 寫 per-directory `.gitignore`

每個資料類目錄一份，第一行註解說明用途，接著 `*` 全擋，再逐一放行。打開目錄就看得到它保留什麼。

範本（`datasets/.gitignore`）：

```gitignore
# datasets/：預設全部不進 git，只保留以下檔案（不要加 !*/，否則 git 會掃描每個子目錄）
*
!.gitignore
!README.md
```

常見變化：

```gitignore
# inputs/：只保留取檔腳本與說明（inputs/<物種>/ 由 <物種>.sh 重建）
*
!.gitignore
!README.md
!*.sh
```

```gitignore
# models/：訓練輸出不進 git（可重跑），只保留說明與 publish/ 的 README
*
!.gitignore
!README.md
!publish/
publish/*
!publish/README.md
```

要放行子目錄裡的檔案，必須三行一組：`!sub/` → `sub/*` → `!sub/<file>`。原因：父目錄被排除時，git 不會進去，裡面的 `!` 規則全部無效。

**放行子目錄只寫明確名稱**（如上面的 `!publish/`），通用的 `!*/` 會讓每個子目錄都被重新納入，git 得掃完整棵樹，且子目錄內的檔案仍需另外處理。

## 3. 精簡 root `.gitignore`

root 只放兩種東西：工具／環境規則（Python cache、venv、編輯器與 agent 目錄），以及**全域副檔名排除**。再對程式需要的設定檔做窄範圍放行。

```gitignore
# 模型與 run artifact（不論放在哪個目錄都不進 git）
*.pth
*.pt
*.joblib
*.pkl
*.pickle
*.onnx

# 陣列與二進位資料
*.npz
*.npy
*.parquet
*.feather
*.h5
*.hdf5

# 基因型原始檔與壓縮檔
*.vcf
*.vcf.gz
*.hmp
*.bed
*.bim
*.fam
*.gz
*.7z
*.tar
*.rar

# 資料類目錄各自用自己的 .gitignore

# 表格、報表、圖片與其他產出
*.csv
*.tsv
*.xlsx
*.xls
*.docx
*.pptx
*.pdf
*.log
*.jpg
*.jpeg
*.png
*.gif
*.svg
*.webp
*.txt
*.json
*.jsonc
*.zip

# 程式需要的設定檔（窄範圍放行）
!/configs/**/*.json
```

依 repo 調整副檔名清單與放行規則。`*.txt`、`*.json` 會吃掉 `requirements.txt`、`package.json`、`tsconfig.json` 這類必要檔，逐一加 `!/<path>` 放行，並在第 5 步的「必須追蹤」清單驗證。

為什麼需要全域副檔名：只寫目錄規則（如 `/models/*/`）的話，放錯位置的檔案會漏網，例如 `publish/x.npz`、`models/publish/m.pt`、`experiments/<x>/x.npz`。

## 4. 已知陷阱

- **父目錄被排除就無法 re-include**：見第 2 步的三行一組寫法。
- **新規則不會 untrack 已追蹤的檔案**：跑 `git ls-files` 找出符合新規則但已被追蹤的檔案（`git ls-files -ci --exclude-standard`），列給使用者，由人決定是否 `git rm --cached`。
- **symlink 對 git 是檔案**：指向 raw data 的 symlink 也必須被忽略，列入第 5 步測試。
- **效能不是顧慮**：git 不會進入被排除的目錄，目錄裡幾千個檔案也零成本（實測：3171 檔的 models/ 加 814 MB 的 static/，`git status` 0.017 s）。用 per-directory 檔是為了可讀性與就近宣告。

## 5. 驗證（宣告完成前必做）

建兩份清單，用 `git check-ignore -q <path>` 逐一測試（路徑不存在也能測）：

1. **必須被忽略**：實際產出的檔案（dataset、模型檔、metrics json、報表、raw data symlink），加上放錯位置的假想路徑：`publish/x.npz`、`publish/x.pt`、`models/publish/m.pt`、`experiments/<x>/x.npz`、raw data 子目錄內的檔案。
2. **必須追蹤**：每一份 `.gitignore`、各 README、取檔腳本、config YAML／JSON、lockfile（`uv.lock`、`requirements.txt` 等）。

```bash
for p in <必須被忽略的路徑...>; do git check-ignore -q "$p" || echo "LEAK: $p"; done
for p in <必須追蹤的路徑...>;   do git check-ignore -q "$p" && echo "WRONGLY IGNORED: $p"; done
git status --short -uall | grep '^??'                         # 只能出現預期的新檔
git status --short -uall | awk '/^\?\?/{print $2}' | xargs -r du -h | sort -h | tail -5   # 最大的 untracked 檔
time git status >/dev/null
```

完成條件：兩個迴圈都沒有輸出、untracked 清單只有預期檔案、最大 untracked 檔不是資料檔、`git status` 在秒級以內。

本 skill 只修改 `.gitignore` 檔，不執行任何改變 git 狀態的指令（`add`、`rm --cached`、`commit` 等）。

## 6. 回報

- 新增／修改的 `.gitignore` 清單與各自保留的檔案。
- 驗證結果：兩份清單的測試數與失敗數、untracked 清單、最大 untracked 檔、`git status` 時間。
- 已被追蹤但符合新規則的檔案（若有），以及建議的處理方式。
