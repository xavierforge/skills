# xavier skills

[English](README.md)

一條有紀律的 agent 交付管線：從規格到合併 PR，涵蓋角色分層派工、分層審查閘、以及經 eval 量測的 skill。在採用 OpenSpec 結構的專案上運作得最好，但多數 skill 也能獨立使用。

這八個 skill 覆蓋從一個成形的 change 到合併 PR 的交付路徑：開工時的分支紀律（`begin`）、執行階段的角色分層派工（`factory`、`section`）、出貨前帶決策帳的分層審查閘（`cross-check`、`vibe-diff`、`preflight`）、以及收尾時對帳後開 PR（`ship`），每個 skill 各自帶一份行為 eval。OpenSpec 是推薦的規格骨幹，而非硬性前置：`factory`、`section`、`spec-viewer` 讀 `openspec/changes/` 佈局，缺它就不能用；`begin` 與 `ship` 在任何專案都能跑；`cross-check`、`vibe-diff`、`preflight` 有 OpenSpec change 目錄時就用，沒有時退回 mini-spec 與 `.review/` 落點。配套的 [`openspec-rules/`](openspec-rules/) 目錄提供這個佈局所依循的模板。

這個 repo 是每個 skill 的正本（single source of truth）。要改就改這裡，不要改安裝出來的副本（下面的 CLI 與手動兩軌都以 symlink 安裝，副本只是連回這棵樹的連結）。

## 安裝

想要完整管線就先設好 OpenSpec（第 0 步，選用），再從下面三軌之一安裝 skill。

### 0. 選用：安裝 OpenSpec

[OpenSpec](https://github.com/Fission-AI/OpenSpec) 給專案 spec 驅動 skill 所讀的 `openspec/changes/` 結構。裝了它才能用完整管線：`factory`、`section`、`spec-viewer` 需要這個佈局，`cross-check`、`vibe-diff`、`preflight` 有它時會用。其餘 skill 不裝也能跑，所以這步是選用的；只想用 `begin`、`ship` 或那幾個獨立審查 skill 的話可以跳過。

除了 OpenSpec，本套件沒有其他外部 skill 依賴。凡是 skill 本文引用了自己不擁有的鄰居指令（`/opsx:verify`、`/code-review`、`/verify`、`/opsx:archive`），都附了缺該指令時的 fallback，所以不會因為缺某個指令而硬性失敗。

### 1. skills CLI（主推）

```
npx skills add xavierforge/skills
```

vercel-labs 的 `skills` CLI 適用於任何遵循 Agent-Skills 標準的 harness（Claude Code、Codex 等）。它以 symlink 安裝，所以 skill 會持續跟著這個 repo 演進。

### 2. Claude Code plugin

```
claude plugin marketplace add xavierforge/skills
claude plugin install xavierforge-skills@xavierforge
```

這個 repo 的 `.claude-plugin/` marketplace 把全部八個 skill 收成一個可安裝的 plugin，供 Claude Code 使用者安裝。

### 3. 手動 symlink（fallback）

一個指令全部連結（冪等，新增 skill 後重跑即可）：

```
for s in skills/*/; do ln -sfn "$PWD/$s" ~/.claude/skills/"$(basename "$s")"; done
```

或只連結單一 skill：`ln -sfn "$PWD/skills/<skill>" ~/.claude/skills/<skill>`。

工具需求：`git` 全域必備；`gh`（GitHub CLI）只有 ship 開 PR 的步驟需要（begin 是純 git）；viewer 類 skill 的腳本需要 `uv` 或任一 `python3`。

## 角色 agents（會派工 skill 的推薦前置）

會派工的 skill（`factory`、`section`、`ship`）把工作交給三個具名角色，而不是交給模型名稱，所以搭配角色陣容一起安裝，體驗最完整。安裝方式見 [`agents/README.md`](agents/README.md)，該檔同時涵蓋 Claude Code 與 Codex 兩種 rendering 及其 degraded mode 差異。沒裝角色陣容時，派工步驟是降級而不是硬失敗：`factory`、`section`、`ship` 都會退回一般 general subagent，帶上目標角色的一句精簡契約繼續跑，並在回報裡註明降級。裝了角色陣容，才有真正的模型分層與 per-role 工具邊界；不派工的 skill 不論如何都不受影響。

## Skills

| Skill                                | 做什麼                                                                                                                                                                      | OpenSpec | 呼叫方式                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------ |
| [`begin`](skills/begin/)             | 兩階段的開工儀式：先把 default branch 同步到乾淨的基底並守住 working tree，等工作可以命名時再開 feature branch                                                              | 無       | 手動，`/begin`           |
| [`cross-check`](skills/cross-check/) | 對某個固定點以來的 diff 做雙軸審查，兩軸各開一個平行 sub-agent、並排回報（standards 軸對照本 repo 記載的規範外加一組固定的壞味道基線，spec 軸對照原始 issue 或 PRD）；把結果持久化成 `review-verdict.json` 供 `/ship` 對帳 | 選用     | 手動，`/cross-check`     |
| [`factory`](skills/factory/)         | 驅動整個 active OpenSpec change，一輪一 section 交給全新 subagent 執行，含計畫關卡、輪數預算與總表；僅限使用者手動觸發                                                       | 必要     | 手動，`/factory`         |
| [`preflight`](skills/preflight/)     | `/factory` 與 `/ship` 之間的出貨前驗收關卡：先對帳該 change 的 Non-Goals 與 `decisions.md` 決策帳，再跑機械層、runtime 實跑與兩層靜態審查，把簽收頁交棒給使用者（在新 session 跑 `/vibe-diff`），最後把每條 finding 分流成修正、翻案請求或登記追蹤，並把每個裁決寫回決策帳                                            | 選用     | 手動，`/preflight`       |
| [`section`](skills/section/)         | 執行階段的工作流：跑一個編號的 `tasks.md` 區段（定位 active change、遵守 dispatch 註記、逐任務 TDD、一個 Conventional Commits 提交、勾選核取方塊、停止）                    | 必要     | 模型可呼叫，`/section N` |
| [`ship`](skills/ship/)               | PR 前的出貨工作流：基底刷新、機械式 diff 掃描、品質閘門、對抗性 PR 前審查、commit 整理、PR 描述；專案事實於執行時推導，沒有設定檔                                           | 選用     | 手動，`/ship`            |
| [`spec-viewer`](skills/spec-viewer/) | 把一個 OpenSpec change 渲染成單一自包含的 HTML 審閱頁：proposal、design、specs、tasks 組成一頁可導覽的手冊式頁面                                                            | 必要     | 手動，`/spec-viewer`     |
| [`vibe-diff`](skills/vibe-diff/)     | 把分支對 merge-base 的 diff 渲染成自包含的審閱頁，對照它實作的 OpenSpec change 來讀；決定性腳本擁有頁面本身，模型只撰寫判斷層 JSON；是 `spec-viewer` 的右側雙生頁，彼此互連 | 選用     | 手動，`/vibe-diff`       |

OpenSpec 欄位說明：**必要**代表這個 skill 讀 OpenSpec change 目錄，沒有它就沒有東西可操作（`factory`、`section`、`spec-viewer`）；**選用**代表存在時會利用 OpenSpec 佈局，不存在時走非 OpenSpec 路徑（`ship` 改為詢問並由佈局推導 spec 位置與合併後儀式；`cross-check`、`vibe-diff`、`preflight` 退回 mini-spec 與 `.review/` 落點）；**無**代表完全解耦（`begin`）。

## 慣例

- **不寫死安裝路徑**：Claude Code 呼叫 skill 時會宣告「Base directory for this skill: <path>」，每份 SKILL.md 都透過這個宣告引用自己的檔案，內文寫作 `<skill-base>/scripts/...`。
- **共用腳本只存一份**：正典副本住在某一個 skill 裡，另一個 skill 以兄弟路徑（`<skill-base>/../<other-skill>/scripts/...`）取用。skill 之間不用 symlink，所以 Windows checkout 或不完整複製都不會壞；唯一的失敗模式是兄弟 skill 沒安裝，而引用方的 SKILL.md 會明說這件事。
- **腳本統一放在 `scripts/`**，只用 python3 標準函式庫或純 bash，且永不要求每專案設定檔：專案事實於執行時推導，有歧義時向使用者確認一次，至多「提議」（絕不要求）記錄到該專案自己的 agent 指示檔。

## Evals

每個 skill 都配一份行為 eval，量的是：在固定的便宜模型上，這個 skill 比「同一模型但沒有 skill」多帶來什麼；做成 `with_skill` 對 `without_skill` 的對照，並以執行後的 git 狀態與輸出來評分，而不是聽執行者自己的敘述；各 suite、方法與逐 skill 的數字都在 [`evals/EVALUATION.md`](evals/EVALUATION.md)。這是 Claude Code 專屬的量測層：`evals/harness/run_eval.sh` 直接呼叫 `claude` CLI 來跑每一組對照，其中的 `claude --safe-mode --dangerously-skip-permissions` 是刻意的、只作用於這個 harness，每次執行都在一個用過即丟的沙盒 checkout 裡進行，跳過互動式的權限詢問正是讓整批能無人值守跑完的原因；這不是對一般 skill 使用的建議，公開後若有掃描工具對這個 flag 報警，是把它脫離沙盒脈絡在讀。

## 可移植性與雙 harness 支援

這個 repo 的目標是對 Claude Code 與 Codex 都有基本支援，不是完全對等。skill 本文與其 Codex 描述子都維持 harness 中性；某個 harness 無法保證的地方，就據實寫出 degraded mode，而不是遮掩過去。

- **用 uv 跑，且僅依賴 Python 內建函式庫**：腳本完全不依賴外部套件，直接從根本避開 venv、pip 和鎖定版本的問題，唯一的假設就是「系統裡有 Python 3」。`uv run` 只是個跨平台的啟動器（沒裝 Python 時它會自己搞定）；沒有 uv 的環境，`SKILL.md` 也會退回用標準的 `python3` 來跑。以後加新腳本也要保持這個原則。
- **基底目錄，任何 harness 皆可**：`<skill-base>` 的慣例是靠 Claude Code 執行時塞入的「Base directory for this skill: <path>」提示。其他 harness 可能沒這功能，遇到這種情況就相對於載入的 `SKILL.md` 來解析路徑。skill 本文寫成「這個 skill 的基底目錄」這種通用概念，不寫死只有 Claude Code 才能用。
- **frontmatter 是 Claude Code 專屬，description 才可攜**：`SKILL.md` 裡的 `disable-model-invocation`、`model` 和 `effort` 只有 Claude Code 看得懂，其他 harness 只讀 `name` 和 `description`。給這些 harness 用的，是每個 skill 在 SKILL.md 旁附的 `agents/openai.yaml` Codex 描述子，內容與 description 同步。另外在 Claude Code 裡設 `disable-model-invocation: true` 還會把該 skill 的 description 從常駐清單拿掉，所以像 begin、ship、spec-viewer、vibe-diff 這種手動觸發的流程，完全不佔用常駐的 context。
- **用「角色」來指定模型，只保留一個刻意綁定的模型**：`ship` 的嚴格 review 會直接要求「目前最強的 review 級別模型」，並回報用了哪一個，這樣就算以後換了模型陣容也不用改 code。`spec-viewer` 目前還是綁定 `model: haiku`（跑腳本最便宜的選擇）；如果哪天這個綁定過時了，就把它改成角色描述，而不是換成新的 model ID。
- **角色陣容：兩個 harness 都支援，且據實寫出 degraded mode**：會派工的 skill 對應三個角色（explore、too-te、sai-hu），而不是模型名，所以陣容可以重新綁定或改由別處託管而不動任何 skill 本文。兩種 rendering 都住在 `agents/`（`agents/claude/*.md` 與 `agents/codex/*.toml`），安裝方式見 [`agents/README.md`](agents/README.md)。某個 harness 撐不起某項保證時（Codex 沒有硬性的 turn 上限、也沒有 per-tool 的封鎖清單），角色契約就以文字承載這個限制，環境不同時 skill 回報狀況而不是卡死；確切差異列在該 README 的 degraded mode 段。
- **Slash command 耦合**：技能說明會講清楚需要什麼事件觸發，把旁邊的 slash command 當作觸發的方法之一，而不是硬依賴（像是 `begin` 的 branch 規則現在是寫「在新工作的第一個 commit 之前」，而不是指定要跑 propose 指令）。未來加新技能時，也要繼續檢查有沒有這種硬性依賴。
