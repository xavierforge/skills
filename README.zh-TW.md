# xavier skills

[English](README.md)

這組專案包含八個 skill，負責把一個變更 (change) 從擬定規格一路護送到合併 PR，完整順序如下：

1. **準備** (`begin`)：把預設分支同步到乾淨基準，再開出一條 feature branch。
2. **實作推進**：`factory` 負責推進整個開發進度，每輪處理一個 section；`section` 則專注執行單一個區塊，逐 task 做 TDD，完成一個 commit 就停。
3. **多重審查**：`cross-check`、`vibe-diff`、`spec-viewer` 與 `preflight` 疊加多重審查閘門，並維護一份決策紀錄 (decision ledger)。
4. **貢獻與合併** (`land`)：對帳、跑對抗式審查、整理 commit，最後寫好 PR body 開出 PR。

以上流程是圍繞著 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 工作流長出來的，所以搭配它進行 SDD 時效果最好。但實際上也只有三個 skill 硬性要求 OpenSpec 的資料夾結構 (詳見下表)；其餘的在任何 repo 都能跑，如果找不到 spec 資料夾，就會自動退回使用 mini-spec 並在 `.review/` 落地，專案內的 `openspec-rules/` 資料夾有提供需要的範本。

另外請記得：這個 repo 是唯一的 source of truth，下面的安裝方式都是以 symlink 為主，所以要改設定就直接改這裡，絕對不要去動安裝出去的副本。

> **關於 mini-spec**
>
> 這是這套工作流特有的名詞，指的是開工時交給 `/begin` 的那幾句「原始意圖」。
> 系統會將它**逐字保存**到 `.review/<branch-slug>/mini-spec.md` 裡 (絕對不會雞婆從對話中幫你生摘要)。
> 當專案缺乏 OpenSpec change 可以參考時，review 類的 skill 就會拿這份檔案當作解讀 diff 的唯一基準。
>
> **實際運作範例**
>
> 假設我們輸入：
>
> `/begin CLI 加上 --json flag；schema 對齊 README 的表格；預設的文字輸出維持不變`
>
> 系統會自動開出一條 feature branch，並把上面這句話一字不漏地存成 `.review/feat-cli-json-flag/mini-spec.md`。
> 之後當我們跑 `/vibe-diff` 審查時，skill 就會直接對照這份 mini-spec 來解釋、評斷這條分支的 diff 到底有沒有符合初衷。

## Skill 一覽

| Skill                                | 核心功能簡述                                                          | OpenSpec | 呼叫方式                  |
| ------------------------------------ | --------------------------------------------------------------- | -------- | --------------------- |
| [`begin`](skills/begin/)             | 先同步預設分支，再開乾淨的 feature branch                                    | 不需要      | `/begin`              |
| [`factory`](skills/factory/)         | 推進進行中的 change，一輪解決一個 section，每輪都會開啟全新 subagent                  | 必要       | `/factory`            |
| [`section`](skills/section/)         | 執行 `tasks.md` 的單一編號 section：逐 task 進行 TDD 並在最後使用單一個 commit，做完就停 | 必要       | `/section N`（模型可自行呼叫） |
| [`cross-check`](skills/cross-check/) | 對 diff 做 standards 與 spec 雙軸審查；留下 verdict 給 `/land` 對帳          | 可選       | `/cross-check`        |
| [`vibe-diff`](skills/vibe-diff/)     | 產出 self-contained 的 diff review 頁面，對照 change 的意圖來讀              | 可選       | `/vibe-diff`          |
| [`spec-viewer`](skills/spec-viewer/) | 把一個 OpenSpec change 渲染成單頁 handbook 式 HTML                       | 必要       | `/spec-viewer`        |
| [`preflight`](skills/preflight/)     | 貢獻前的驗收閘門：對帳、跑各審查層、把 findings 逐一裁決                               | 可選       | `/preflight`          |
| [`land`](skills/land/)               | 同步遠端預設分支的最新基準、執行品質閘門、對抗式審查、整理 commit、寫 PR body            | 可選       | `/land`               |

_(備註：**必要** = 沒 `openspec/changes/` 就無事可做；**可選** = 有就用，沒有就走非 OpenSpec 路徑；**不需要** = 完全解耦。)_

`land` 原本叫 `ship`，因為 Claude Code 出了同名的 skill 才改名；如果你是用 symlink 安裝的，重跑一次安裝迴圈，再把 skills 目錄裡殘留的 `ship` 連結刪掉即可。

## 安裝方式

> **TL;DR**
>
> 用你的 agent (Claude Code 或 Codex) 打開這個 repo，直接對它說 **「照 [AGENTS.md](AGENTS.md) 的 setup runbook 做」**，系統就會一口氣幫你把 skills、角色名單 (role roster) 和專案的 OpenSpec 規則範本全裝好，強烈建議完整跑完這個步驟，因為這是發揮所有 skill 實力的基礎！
>
> 如果想手動來，請參考以下做法。

### 0. OpenSpec（可選）

要跑完整 pipeline 就得先裝 [OpenSpec](https://github.com/Fission-AI/OpenSpec)，但如果只想使用 `begin`、`land` 或獨立審查的 skill 可以直接跳過。除此以外，本專案就沒有其他外部相依套件，skill 內文提到了隔壁的指令 (`/opsx:verify`、`/code-review` 等)，系統都有寫好 fallback，不用擔心會直接掛掉。

### 1a. skills CLI（推薦）

```bash
npx skills add xavierforge/skills
```

vercel-labs 的 `skills` CLI 支援所有遵循 Agent-Skills 標準的 harness（Claude Code、Codex 等），而且用 symlink 安裝，repo 更新時已裝好的 skill 也會自動跟上。

### 1b. Claude Code plugin

```bash
claude plugin marketplace add xavierforge/skills
claude plugin install xavierforge-skills@xavierforge
```

### 1c. 手動 symlink（備援）

```bash
for s in skills/*/; do ln -sfn "$PWD/$s" ~/.claude/skills/"$(basename "$s")"; done
```

這招可以重複跑 (idempotent)，新增 skill 後再跑一次即可。若想單獨裝一個 skill 的話指令是：`ln -sfn "$PWD/skills/<skill>" ~/.claude/skills/<skill>`。

需要的工具：`git` 一定要有；`gh` 只有 land 開 PR 那一步用到；viewer 類 skill 的 script 需要 `uv` 或任一 `python3`。

### 2. Role agents（推薦）

會自動派工的 skill (`factory`、`section`、`land`) 是把任務發包給三個「具名角色」，而不是綁死特定模型。

請照 [`agents/README.md`](agents/README.md) 的說明安裝 (Claude Code 和 Codex 版都有)。沒裝也不會壞，派工時會自動降級成帶著一句話契約的普通 subagent 繼續跑，並在回報裡註明降級；但裝了才能擁有真正的模型分級和明確的工具邊界。

## 慣例與原則

- **不寫死安裝路徑**：skill 內文一律用 `<skill-base>/scripts/...` 來抓自己的檔案，從 harness 呼叫時給的 base directory 動態解析。
- **共用 script 只存一份**：正本固定放某個 skill 裡，鄰居要用就走 sibling 路徑 (`<skill-base>/../<other-skill>/scripts/...`)，skill 之間絕對互相不 symlink；唯一的失效模式是「鄰居沒裝」，遇到時提示詞會直接明講。
- **乾淨的腳本環境**：skill 的所有 script 都收在 `scripts/`，只用 python3 標準函式庫或純 bash，永遠不依賴專案層級的設定檔，專案細節都在執行當下動態推導，真的猜不到就直接開口問使用者。

## Evals

每個 skill 都有行為評測：用同一個便宜模型分別跑 `with_skill` 和 `without_skill` 兩組，最後直接看 git 狀態和產出結果來評分，評分方式和分數列在 [`evals/EVALUATION.md`](evals/EVALUATION.md)。

harness 裡的 `claude --safe-mode --dangerously-skip-permissions` 是為了讓整批評測可以在沒有人類干預的情況下跑完，範圍限定在用完即丟的沙盒 checkout，不是鼓勵這樣用哦，平常使用時請自行斟酌。

## 跨平台支援（Claude Code + Codex）

這個 repo 提供的是雙平台的基本支援，不追求完全對等；只要 harness 撐不住的地方，將一律誠實寫明降級狀況：

- **Script 只依賴標準函式庫**：沒有 venv、pip 或鎖版本的問題；`uv run` 只是個跨平台的啟動器，本專案有明寫 `python3` 當作備援。
- **`<skill-base>` 在任何 harness 都成立**：Claude Code 在呼叫時會主動宣告 base directory；其他平台則以載入 `SKILL.md` 的位置為準進行解析。
- **Frontmatter 是 Claude Code 專屬**：其他 harness 只讀 `name`/`description`；每個 skill 都多附了一份 `agents/openai.yaml` 給 Codex 讀，設定 `disable-model-invocation: true` 是為了讓手動呼叫的儀式類 skill 不去佔用常駐清單 (零常駐 context)。
- **靠角色描述路由模型**：例如 `land` 會要求「當下最強的 review 模型」，而不是綁死某個型號，全場唯一刻意綁定的只有 spec-viewer 的 `model: haiku` (因為要找能跑 script 的最便宜模型)。
- **雙平台都有 agent roster**：提供 `agents/claude/*.md` 和 `agents/codex/*.toml` 兩種版本；Codex 那邊的技術落差 (沒硬性回合上限、沒工具黑名單) 全都條列在 [`agents/README.md`](agents/README.md)。
- **不硬性綁死 slash command**：skill 內文只描述「需要發生的事件」，鄰居指令只是解法之一，如果環境裡沒有指令可以 call，也有 fallback 可以走。
