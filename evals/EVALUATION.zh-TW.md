# Skill evaluations：結果與規格

[English](EVALUATION.md)

簡單來說，這個資料夾放的是本專案各個 workflow skill 的行為驗證 (behavioral evaluations)，同時也是這些驗證如何設計、執行、評分與回報的唯一事實來源 (single source of truth)。其中每個驗證都只專注於探討「在固定的模型下，有裝這個 skill 比沒裝到底多了什麼價值？」這些納入版本控制的輸入檔包含 case 設定 (`cases/`) 和 harness (`harness/`)；而彙整與檢視工具，則直接取自 Anthropic 官方的 `skill-creator` skill。

建議的閱讀順序是：先看數字，再看方法。下面的跨 harness 對照表是重點，至於底層邏輯與架構 (Schema、檢查類型、執行紀律、鐵律) 全都收在後面的 [「How the evals work」](#how-the-evals-work)，需要深究時再翻就好。

## 結果：跨 harness 對照（2026-08-28）

這套驗證現在有兩個執行器 (executor)：Claude Code (`claude -p`，配上 `EVAL_MODEL=sonnet`) 以及 Codex (`codex exec`，配上 `EVAL_MODEL=gpt-5.6-terra` 並透過 `EVAL_EXECUTOR=codex` 啟用)。在這一輪測試中，我們讓兩個執行器把八個 suite 各跑了一遍 (每個 arm 跑一個 run)，而且 case 檔、harness、事後補判的 judge (同樣是用 `sonnet`) 都完全一致。

要注意的是，Codex 那邊帶有派工 (dispatch) 斷言的四個 suite (`land`、`section`、`factory`、`preflight`)，是在 `~/.codex/agents/` 已經裝好 [role roster](../agents/README.md) 的狀態下測的，這樣 collab 的 `spawn` 工具才有具名角色可以派發；另外四個沒有派工斷言的 suite 則不受 roster 影響。

表上的數字是 full-assertion 總分 (機器自動判斷 + backfill 補判的 `llm_judged` 分數)，格式是 passed/total。各 suite 原始的給分細節都躺在 `results/<suite>/iteration-N/` 裡面，iteration 編號寫在下表 (Claude Code / Codex)。

| Skill         | Iter (cc/cx) | Claude with | Claude w/o | Codex with | Codex w/o |
| ------------- | ------------ | ----------- | ---------- | ---------- | --------- |
| `begin`       | 9 / 8        | **11/11**   | 6/11       | **11/11**  | 8/11      |
| `land`        | 6 / 7        | 13/14       | 7/14       | 13/14      | 7/14      |
| `section`     | 4 / 5        | **14/14**   | 10/14      | **14/14**  | 10/14     |
| `factory`     | 4 / 5        | 18/22       | 6/22       | 11/22      | 8/22      |
| `vibe-diff`   | 4 / 3        | **12/12**   | 2/12       | **12/12**  | 3/12      |
| `cross-check` | 4 / 3        | 3/4         | 1/4        | 3/4        | 1/4       |
| `spec-viewer` | 4 / 3        | **8/8**     | 1/8        | **8/8**    | 1/8       |
| `preflight`   | 11 / 12      | **15/15**   | 8/15       | 14/15      | 7/15      |
| **總計**      |              | **94/100**  | 41/100     | **86/100** | 45/100    |

單看機器自動判分的子集 (machine subset)，兩個執行器表現很接近：`with_skill` 是 66/69 (Claude) 對 63/69 (Codex)；baseline (沒裝 skill) 則是 29/69 對 32/69。這證明了 skill 的價值跨平台依然成立：**Claude Code 上進步了 +0.53，Codex 上進步了 +0.41**，而且雙邊 baseline 分數也很相近 (41/100 對 45/100)。

至於為什麼會掉分則是因為以下理由：

- **Codex 的 `factory` 卡在 plan-approval 審查閘門 (掉了 11 分幾乎都是因為這點)**：eval-1 和 eval-4 的 run 跑到閘門就停下來等使用者核准，但驗證是自動化腳本，沒人可以回答它，結果就是一整個回合都沒跑，後續的斷言 (包含 rounds、ledger、`/opsx:verify`、lane plan) 當然就跟著全滅。
- **`factory` eval-2 雙平台、雙 arm 全掉**：因為模型拒絕時沒講「只服務 OpenSpec 專案」，也沒指路「先 propose 一個 change」。這是 `SKILL.md` 提示詞寫得不夠精準的措辭缺口。
- **Claude 的 `factory` 掉了兩列**：因為 judge 讀到的 transcript 紀錄被截斷了，在後段派工與最終 ledger 出現前就結束。這兩列的分數請當作下限來看，不是它真的沒做。
- **其餘失分都是 baseline 本來就該掛掉的地方**：像是沒派工就自己 inline 硬做、不問使用者就自己隨便挑 change，或是本該把 lane 交給使用者卻自己 fan-out。這些落差，正是 Δ (加上 skill 後的進步幅度) 的本體。

要注意，派工本身雙邊都沒掉分：Codex 會透過 collab 工具去 spawn roster 裡的角色 (例如註記為 `sai-hu` 的段落就真的交給 `sai-hu` child 去跑)。判斷派工的依據，是去收割每次 spawn 留下來的紀錄 (細節見下方 Codex executor 說明)。如果把派工相關的分數拔掉，`with_skill` 是 88/92 (Claude) 對 82/92 (Codex)。

### 該怎麼解讀 Δ (進步幅度)

Δ 真正衡量的是 skill 能不能賦予模型「結構化的判斷力」，也就是新增了什麼能力。
如果是針對那些把重複儀式固化下來的 skill (ritual-automation 類，例如 `begin`、`spec-viewer`)，真正的 KPI 是裝了之後的「服從度」跟「穩定度」，而不是 Δ。

按照這個標準，這裡的八個 suite 可以被分成三類：

1. **Ritual-automation** (`begin`、`spec-viewer`)
2. **Hybrid** (`land`、`vibe-diff`)
3. **Judgment-structure** (`cross-check`、`factory`、`section`、`preflight`) — 只有這類才是看 Δ 為準。

有時候某些測項雙邊都過了 (Δ 為零)，這是故意的，它們是拿來盯緊模型有沒有服從儀式、有沒有偷偷漂移的「哨兵」，不是廢柴測項。就算 baseline 變聰明導致 Δ 縮水，也不代表我們要狂加規則去考倒它；我們該做的是改用便宜模型去測，而不是硬加料直到 baseline 再次掛掉。

### Codex executor 特殊機制

設定 `EVAL_EXECUTOR=codex` 會讓每一組驗證改走 `codex exec` 而不是 `claude -p`，但所有的開發紀律完全一樣：

- **嚴禁用 API Key，只能用 Vendor 訂閱**：Claude 驗證器強制 `ANTHROPIC_API_KEY` 等環境變數必須清空；Codex 也一樣，要求把 `OPENAI_API_KEY` 清空，乖乖走 ChatGPT 登入。跑 Codex 模式還得明確指定 `EVAL_MODEL`。
- **乾淨的沙盒啟動 (Hermetic 啟動)**：指令是 `codex exec --ignore-user-config --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json` (對標 Claude 的安全模式)。有個大坑要注意：`--ignore-user-config` **擋不住** `~/.codex/agents/`！只要你裝了 role roster，Codex arm 就是看得到它。因為同一個執行器的兩個 arm 看到的環境一致，所以內部的 Δ 不受影響；但如果你要比較安裝 roster 前後的輪次，一定要把這點放心上。
- **證據收集一視同仁**：`result.md` 跟 `transcript.md` 一律從 `codex.stream.json` (也就是權威紀錄) 無條件重建出來。
- **流量限制與系統滿載 (capacity) 的處理差異**：遇到 `401`/`429`/quota 這種限流訊號，就是整批停損煞車，絕不硬擠重試 (跟 Claude 端一樣)。唯一的例外是 provider 回報「伺服器滿載 (model is at capacity)」：這種中途死掉、沒吐出任何輸出的短暫故障，允許拉開間距重試，因為失敗的回合沒留下東西，不可能靠重試灌水。
- **派工證據只存在 session rollout，不在 stream 裡**：collab `spawn` 工具只能叫出 `~/.codex/agents/` 裡有的 agent。但 Codex 在回報 json 時，只會給一個沒接收者的 `wait` 標籤；子 agent 到底做了什麼，全躺在 `$CODEX_HOME/sessions` 底下的 rollout 檔案裡 (靠 `parent_thread_id` 來對)。我們會用 `harness/codex_transcript.py` 去收割這些 rollout，把它們塞進 transcript 的 `[dispatch]` 紀錄裡，judge 就是看這段來給分。

## 歷史與兩種評分制度

那些更早期的歷史輪次 (例如 2026-08-06 的表格、LLM 自己當裁判的舊輪次等) 都被濃縮進 [`history.md`](./history.md) 了。在那邊你會看到兩種評分制度，**千萬不要拿來混著比**：

- 剛跑完的一輪，分數都是 **machine subset (純機器判)**：腳本 `check.py` 會把需要人為或 LLM 判斷的 `llm_judged` 項目先標記為 `passed: null`，延後處理，不計入通過率。
- 事後跑 `backfill.py`，會把延後的項目交給 LLM 補判，算成 **full-assertion 總分**，兩者並排顯示、永不混合：`summary.pass_rate` 就是機器判的分數，`summary.total_pass_rate` 是加總分。

過去得到的血淚通則現在依然適用：純機器判 (machine subset) 絕對會低估 judgment 類 skill 的價值 (因為最難判斷的情境都被延後了)；而 backfill 補判可能會放大也可能縮小 Δ，所以兩種分數都要看。能力強的模型本來就能搞定 happy path，skill 真正的價值，在於模型搞砸時，它能不能把護欄架好。

## How the evals work (底層怎麼跑)

### 九個驗證 Suite

| Suite                                     | 受測 skill    | 情境數 | 頁面                                                                                     |
| ----------------------------------------- | ------------- | ------ | ---------------------------------------------------------------------------------------- |
| [`begin`](./history.md#begin)             | `begin`       | 3      | dirty-tree 防護、被佔用的 lane 開新工作、乾淨的 maintainer 命名                          |
| [`land`](./history.md#land)               | `land`        | 3      | 停在預設分支、ready-to-land 狀態、Step 0c 對帳                                           |
| [`section`](./history.md#section)         | `section`     | 3      | 單 section happy path、兩個 active change、dispatch 註記                                 |
| [`factory`](./history.md#factory)         | `factory`     | 4      | 完整三 section 迴圈、無 active change 時拒絕、plan-gate 重寫、平行 lane 交接             |
| [`vibe-diff`](./history.md#vibe-diff)     | `vibe-diff`   | 2      | 無 spec 來源拒絕（hardened contract）、mini-spec happy path                              |
| [`cross-check`](./history.md#cross-check) | `cross-check` | 1      | 雙軸（standards + spec）verdict 產物                                                     |
| [`spec-viewer`](./history.md#spec-viewer) | `spec-viewer` | 2      | 渲染 change 頁面、產出 zh-TW gloss                                                       |
| [`preflight`](./history.md#preflight)     | `preflight`   | 2      | 對照 Non-Goals 和 decision ledger 裁決三個 findings、缺席層誠實回報並在 ledger 留 caveat |
| `retro`                                   | `retro`       | 3      | 尚未跑過：第一次出現只記帳、第二次出現提出 proposal 並停下等核准、沒證據的說法直接剔除 |

每個 suite 最頂層的 `skill_name` 就代表它專心測哪個 skill。

### 每個驗證 (eval) 到底在量什麼

每個情境都跑在**各自隔離、斷網的 git 沙盒裡**。我們會把沙盒建置到指定狀態 (例如樹髒髒的、分支被佔用等)。同一個沙盒，同一個模型會跑兩條 **arm**：

- **with_skill**：被告知去讀該 skill 的 `SKILL.md` 並照做。
- **without_skill (baseline)**：只給任務提示，不給 skill，讓它自由發揮。

機器判看的是**最終的 git 狀態和該 run 自己的產出**，不信 executor 的自述；真正需要判斷力的則延後給 backfill grader。

**Hermetic 啟動是承重的。** 每個 executor 都在剝掉 ambient context 的狀態下啟動（`claude --safe-mode`；`codex exec --ignore-user-config`）：沒有使用者或專案指示、沒有 auto-memory。這讓兩個 arm 之間恰好只差一個變數；這個 repo 的全域指示帶著跟 skill 重疊的 commit 紀律，若被自動注入，等於偷偷把同樣的指導塞給 baseline。當 `SKILL.md` 自己說要*讀* repo 裡的 `AGENTS.md` 時，那個檔案仍在 sandbox 裡、隨時可讀：hermetic 拿掉的是 ambient 自動載入，不是 skill 自己的明確查閱。

**skill 怎麼進到 with_skill arm**：沒有安裝、沒有自動載入。`with_skill` 的 prompt 直接給 `skills/<skill_under_test>/SKILL.md` 的絕對路徑，要求讀了照做，`<skill-base>` 引用對著 repo checkout 裡該 skill 的目錄解析；`without_skill` 只拿到裸任務。沒有任何東西被複製進任何 skills registry，hermetic 模式也從不擋明確去讀 checkout 裡的檔案。

**網路隔離是「指令加 fixture」，不是強制力**：executor 是在權限全開下跑的，沒有任何一層會擋網路指令。`git push` 推不出去是因為 `origin` 是本地 bare repo，但 `gh` 和 `curl` 只是被 ground rules *禁止*而已；這些 run 請一律跑在用完即丟的 checkout 上。

### Schema v1：`skills-eval/1`

Case 檔（`cases/<suite>.json`）是每個 eval 的**正典、版本控制**的陳述。以下是 schema；checker（`harness/check.py`）是它唯一的解讀者。

```json
{
  "schema": "skills-eval/1",
  "skill_name": "<suite 名>",
  "evals": [
    {
      "eval_id": "<穩定的 kebab id>",
      "skill_under_test": "<skill>",        // 可省略；預設同 skill_name
      "prompt": "<使用者那一句話，逐字>",
      "fixture": "<suite>/<n>",             // 對應 harness/build_sandbox.sh 的鍵
      "arms": ["with_skill", "without_skill"],
      "expected_output": "<一段話的人類摘要>",
      "expectations": [
        {"text": "<人類可讀的斷言>", "check": { "type": "...", ... }}
      ]
    }
  ]
}
```

每個 expectation 都是**人類可讀的 `text`** 配一個**型別化的 `check`**。原則：**機器能判的一律給機器判；只有真正的判斷題留給 `llm_judged`**，而且每個 `llm_judged` 的 rubric 都要寫清楚*為什麼*非它不可。

#### Check 類型詞彙表

路徑解析規則：`file_*`、`json_check`、`changes_confined_to` 作用在 **sandbox 的 git tree**；`text_contains` 作用在**該 run 自己的產出**（`result.md`、`transcript.md`、`PR_BODY.md`，由 `source` 選擇）。`git_log_count` 的預設 `base` 是 fixture 的初始 commit。

**Git／檔案系統狀態（run 之後的 sandbox）：**

| 類型                  | 欄位                                                                                                      | 通過條件                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `git_log_count`       | `base?`, `range:[min,max]`                                                                                | HEAD 相對 `base` 新增的 commit 數落在範圍內                           |
| `commit_subject`      | `which:"head"\|"added"`, `regex`                                                                          | tip 的 subject（`head`）或每個新增 subject（`added`）符合 `regex`     |
| `head_branch`         | `equals?` \| `regex?`                                                                                     | 目前 checkout 的分支名符合                                            |
| `branch_exists`       | `name`, `expect?:true`                                                                                    | 指名的本地分支存在（`expect:false` 則必須不存在）                     |
| `branch_count`        | `range:[min,max]`                                                                                         | 本地分支數落在範圍內                                                  |
| `is_ancestor`         | `ancestor`, `descendant`                                                                                  | `ancestor` 可從 `descendant` 回溯到                                   |
| `ref_equals`          | `left`, `right`                                                                                           | 兩個 ref 指向同一個 commit（fast-forward 檢查）                       |
| `git_clean`           | `expect?:true`                                                                                            | working tree 乾淨（`expect:false` = 必須保持 dirty）                  |
| `git_no_stash`        | 無                                                                                                        | stash 清單是空的                                                      |
| `file_exists`         | `path?` \| `paths?`, `expect?:true`                                                                       | 檔案存在（`expect:false` 則必須不存在）                               |
| `file_size`           | `path`, `min_bytes?`, `max_bytes?`                                                                        | 檔案存在且大小落在界線內                                              |
| `file_contains`       | `path`, `needle?`\|`needles?`\|`regex?`\|`regexes?`, `present?:true`                                      | 檔案內容符合（多個 `needles`/`regexes` 全要中；`present:false` 反轉） |
| `json_check`          | `path`, `min_keys?`, `has_keys?`, `absent_keys?`, `equals?:{dotted:val}`, `array?:{path,has_keys?,enum?}` | JSON 可解析且滿足給定的結構斷言                                       |
| `changes_confined_to` | `prefix`                                                                                                  | `git status` 回報的每個路徑都在 `prefix` 底下                         |

**Run 產出（該 arm 自己的回覆／transcript）：**

| 類型            | 欄位                                                                                                            | 通過條件                                                                |
| --------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `text_contains` | `source:"result"\|"transcript"\|"pr_body"\|"any"`, `needle?`\|`needles?`\|`regex?`\|`regexes?`, `present?:true` | 選定的產物符合（多個 `needles`/`regexes` 全要中；`present:false` 反轉） |

**判斷題備援：**

| 類型         | 欄位     | 行為                                                                                      |
| ------------ | -------- | ----------------------------------------------------------------------------------------- |
| `llm_judged` | `rubric` | `check.py` 延後它（`passed: null`）；之後的 `backfill.py` 把裁決折回同一份 `grading.json` |

這份詞彙表是**開放的**：之後可以加新的機器類型（只有 checker 需要學會它），而一個 `llm_judged` expectation 一旦變得可機器判定，就立刻升級成機器 check。

#### `llm_judged` 怎麼補判

`check.py` 是決定性的、不呼叫任何模型，所以它把每個 `llm_judged` expectation **延後**：該列寫成 `passed: null`、附上 rubric，從統計中排除而不是當作失敗。因為評分是決定性的，`fingerprint.checker_sha256` 就完整地識別了所有機器裁決。

判斷本身是**獨立的補充 pass**：`harness/backfill.py <suite> <iteration>`，在主迴圈跑、永不進 subagent。這也是 gitignored 的 run workspace 要保留的原因：延後的列可以事後補判，不用重跑。`backfill.py` **只碰** `passed: null` 的列，每列用一次 `claude -p`（subscription、便宜檔、嚴格 serial、遇到限流即停）判定，餵入該列的 `text` 加 `rubric`，以及該 run 自己的 `result.md`、`transcript.md`、`git-state.txt`，然後把 `{passed, evidence}` 以 `verdict_source: "grader"` 合併回去。judge prompt 的 transcript 預算是 60k 字元、超限採頭尾保留的中段省略，所以收尾階段的證據不會被截掉。在 codex 輪之後跑 backfill 時，記得**不要**帶著 `EVAL_MODEL`：這個變數在這裡指的是 judge 的模型，不是受測模型。

因為 grader 是 LLM，它的身分記在獨立的 `fingerprint.grader` 區塊，跟 `checker_sha256` 分開：

```json
"grader": {"model": "<model>", "rubric_sha256": "<該 run 的 llm_judged (text, rubric) 列的 sha256>", "harness_commit": "<short HEAD>"}
```

summary 把兩種制度並排呈現：`summary.pass_rate` 維持 machine subset；backfill 加上涵蓋機器加 grader 列的 `summary.total_pass_rate`，並把 `run_summary_total` 區塊折進 `benchmark.json`。

### Fingerprint 區塊

每份 `grading.json` **必須**帶 `fingerprint`，讓結果能追溯到產生它的確切條件；由 `run_eval.sh` 的 normalize pass 蓋章：

```json
"fingerprint": {
  "checker_sha256": "...", "harness_commit": "...",
  "skill_name": "...", "skill_commit": "...", "iteration": 2,
  "model": "...", "runs": 1,
  "timestamp": "...", "environment": "local",
  "execution": {"arm_rc": 0, "stderr_scan": "clean", "model": "...", "executor": "codex"},
  "grader": {"model": "...", "rubric_sha256": "...", "harness_commit": "..."}
}
```

`execution` 記錄每個 arm 的執行結果（rc、stderr 的認證／限流掃描，codex arm 另記 executor），讓執行紀律的宣稱單靠收回來的 JSON 就能稽核。`grader` 只在 backfill 之後出現；純機器判的輪次沒有它。

### Driver 與 skill-creator 的契約

`harness/run_eval.sh <skill> <eval_id> [runs] [iteration]` 一口氣跑完一個 eval（或 `all`）的整條 pipeline：建 sandbox、跑各 arm（`EVAL_EXECUTOR` 選 CLI）、快照 git 狀態、用 `check.py` 評分、normalize、彙總、收成。它自己不帶任何評分邏輯。skill-creator 只貢獻彙總（`aggregate_benchmark.py`）和 viewer（`eval-viewer/generate_review.py`）；兩者都只讀目錄契約（`iteration-N/eval-*/<arm>/run-*/grading.json` 加 `eval_metadata.json`），從不碰 sandbox 的 git tree。`harness/snapshot.sh` 把 `git-state.txt` 記進每個 run 的 `outputs/` 當證據。

### Iteration 規則

Iteration 是**每個 skill 各自編號**的（`results/<skill>/iteration-N/`）。每一輪都記下當時受測 skill 的 git hash（`fingerprint.skill_commit`）；跨 skill 的可比性來自那個 hash，永遠不是共用的 iteration 計數。

### Baseline（arm）規則

標準形式是 `with_skill` 對 `without_skill` 加一欄 Δ。`old_skill` arm（用 `git archive` 凍結的舊版 `SKILL.md`）是選配：只為了驗證某次 skill 升級沒有回歸的那一輪臨時建、在報告裡明確標註，永遠不是常設 fixture。

### 可重現性：鐵則

1. **可重現三件組都在版本控制裡。** 一個 run 由 **case**（`cases/<suite>.json`）、**fixture**（`harness/build_sandbox.sh`）、**driver**（`harness/run_eval.sh`）定義，三者都在 git 裡。不能從這三者重建的情境，就不是 eval。
2. **執行環境用完即丟。** 只存在於執行環境裡的東西，一律視同不存在。
3. **只有小 JSON 回家。** 一輪跑完帶回 repo 的只有 `grading.json` 加 fingerprint（`results/<skill>/iteration-N/`）；每個 run 的 sandbox、transcript、benchmark blob 都可重生，一律 gitignore。
4. **沒有輪次就沒有引用。** 一輪的 `grading.json` + fingerprint 帶不回來，就當那輪從來沒跑過。

> 鐵則 1 的由來：早期某個 suite 的 sandbox 是在 Codespace 裡手工搭的、從未進版本控制；環境一消失，整個 suite 就無法重現。fixture 現在住在 `build_sandbox.sh` 裡，正是為了讓這件事不再發生。

### Executor ground rules

以下是交給每個 executor run 的固定指示。**實際生效的是英文版 `EVALUATION.md`**：`run_eval.sh` 從那份檔案逐字抽出 blockquote 塞進 prompt，此處只是對照翻譯，改這裡不會改變 eval 行為。

> 你正在一個「隔離、離線」的 git sandbox 裡執行一個任務，這是 skill benchmark 的一部分。你是以 hermetic 方式啟動的（`claude --safe-mode` 或 `codex exec --ignore-user-config`）：沒有載入任何 ambient context（沒有使用者／專案指示、沒有 auto-memory），所以兩個 arm 從同一張白紙起跑，受測 skill 是唯一的變數。遵守以下規則：
>
> - 你的工作目錄是 prompt 給你的 sandbox 路徑。先 `cd` 進去，然後只在裡面操作。唯一可以讀的外部檔案是 prompt 明確指給你的 skill 檔。
> - 離線：`origin`（如果有）是本地 bare repo，所以 `git fetch` 沒問題，但絕對不要跑 `git push`、`gh` 或任何真正需要網路的指令。流程走到 push／`gh pr create` 時，停下來，回報你「本來會執行」的確切指令；不要嘗試執行。
> - 把任務提示當成使用者在這個 repo 裡對你打的字。你跑在便宜的執行模型上。
> - 如果 prompt 指名了要遵循的 skill，讀那份 SKILL.md 並嚴格照做，`<skill-base>` 的 script 引用對著給定的 base 目錄解析。沒有指名 skill 就用你自己的最佳判斷（baseline）。
> - 如果你的 harness 有 subagent dispatch 工具（Agent/Task），流程需要派工時就用它，並註明你用了哪個模型。如果沒有這種工具，就 inline 把那一步做掉，並明確說明。
> - 專案的品質閘門（如適用）是 `make check`（見 AGENTS.md）。
>
> 完成時（或停下來詢問／阻擋時），把以下寫進指定的 outputs 目錄：
>
> 1. `transcript.md`，誠實的敘述：你跑過的關鍵 git／測試指令與必要輸出、決策點；如果你停下來詢問或阻擋，逐字引述你會給使用者的問題或阻擋訊息。註明你刻意「沒做」什麼、為什麼。
> 2. `result.md`：你最終要給使用者的回覆。
> 3. （僅 land）`PR_BODY.md`：你擬的 PR body（如果有）。
>
> 把 git repo 留在最終狀態（不要清理或還原）。以 2-3 句話總結作答。

### 執行紀律

- 跑評測一律走 **executor 自家 vendor 的 subscription**，絕不走 API key：Claude executor 要求 `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` 未設，Codex executor 要求 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 未設。設了 driver 直接 abort。
- **嚴格 serial**，最便宜的情境先跑當哨兵。遇到任何 `401`／`429`／限流或用量上限訊號，**立刻停**并回報；不重試、不擴散。唯一例外是 provider 的 **capacity** 錯誤：暫時性、不產生可評分的輸出，可以拉開間距重試。
- 巢狀的 executor 呼叫（`claude -p` 或 `codex exec`）永遠在**主執行迴圈**裡跑，絕不放進 subagent 的 prompt：安全分類器會擋 subagent 裡的 `--dangerously-skip-permissions`（實際觀察過兩次）。
- 承重假設一旦破掉，**停下來回報**，不要當場自行發明 workaround。

### 目標結構

```
evals/
  EVALUATION.md              本檔（英文版）：結果 + schema／規則的唯一來源
  EVALUATION.zh-TW.md        本檔的繁體中文對照（ground rules 以英文版為準）
  cases/<suite>.json         schema v1：情境 + 型別化 expectations
  harness/build_sandbox.sh   sandbox 建置（一個 case 對一個 fixture 鍵）
  harness/run_eval.sh        一口氣跑完的薄 driver（build -> arms -> grade -> aggregate；EVAL_EXECUTOR 選 claude 或 codex）
  harness/check.py           唯一的通用 checker（機器判的唯一評分者；解讀 schema v1）
  harness/backfill.py        llm_judged 補充 grader（補判延後的列，加上 total_pass_rate）
  harness/codex_transcript.py  codex 產出重建器（stream + child session rollouts -> transcript.md/result.md）
  harness/snapshot.sh        run 後的 git 狀態記錄器（證據放 outputs/）
  results/<skill>/iteration-N/   grading.json + benchmark.json（只收小 JSON）
  history.md                  各 suite 的濃縮發展軌跡
```

---

各 skill 的濃縮發展軌跡（包含被取代的單 executor 輪次）見 [`history.md`](./history.md)。
