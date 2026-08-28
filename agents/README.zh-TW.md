# Role agents

[English](README.md)

## 存在的理由

簡單來說，這個專案多數 Skill 在派發任務時，為了有更好的執行成果，會使用以下三個自訂的 sub-agent：

- **`explore` (唯讀偵察)**：負責找檔案、追蹤程式碼或是搞懂「這東西在哪、怎麼運作」，結論會附上檔案和行號 (file:line 引用)，但絕對不會改動任何程式碼。
- **`too-te` (機械化執行)**：專門處理已經規格化的任務，例如批次修改、照著 checklist 檢查或抽取資料，但前提是得給它明確的目標、範圍和完成條件。
- **`sai-hu` (實作主力)**：需要判斷力的開發工作就交給它！包含開發新功能、解 bug、重構，或者是 `too-te` 連續卡關兩次以上的難題。

這套機制的重點在於：`SKILL.md` 內永遠只寫角色名稱，所以之後不管是要換模型還是換平台，原本寫好的 `SKILL.md` 都不用改，而 `agents/claude/` 和 `agents/codex/` 只是這套契約在不同平台上的實作，核心規則是一樣的，只差在設定檔格式不同。

## 安裝方式

### Claude Code

建議把 `agents/claude/` 裡面的 `.md` 檔 symlink 到 `~/.claude/agents/`，如此一來，當專案更新時，這些自訂的 sub-agent 也會同步升級：

```bash
for f in agents/claude/*.md; do ln -sfn "$PWD/$f" ~/.claude/agents/"$(basename "$f")"; done
```

### Codex

請直接把 `agents/codex/` 裡的 `.toml` 複製到 `~/.codex/agents/`：

```bash
mkdir -p ~/.codex/agents && cp agents/codex/*.toml ~/.codex/agents/
```

注意，Codex 目前 (codex-cli 0.150) 比較不靈活，有兩個限制讓「直接複製」成為唯一可用的安裝方式：

- **不支援 Symlink**：清單雖然看得到，但實際跑起來會報錯 (agent type is currently not available)，所以如果改了設定檔，記得重新複製一份。
- **只吃全域路徑**：它只會讀取 user-wide 的資料夾，官方文件寫的專案層級 `.codex/agents/` 實際上是抓不到的。

_(補充：Codex 的工具清單是動態生成的，沒放檔案前你連 role 參數都看不到，放進去後才會出現。)_

## 任務派發 (Dispatch)

兩個平台裝好後都不需要在全域 CLAUDE.md 或 AGENTS.md 搞複雜的模型路由設定，在腳本裡寫一句「dispatch the `too-te` role」，系統就會自己搞定：

- **Claude Code**：會走 Agent tool 的 subagent 機制。
- **Codex**：會透過 spawn 工具的 `agent_type` 參數載入對應指令，並套用 TOML 裡訂下的 model 和 reasoning effort。注意，在 Codex 中只有透過正確的參數 (`agent_type`) 才能真的叫出角色；如果只是把 task 或 subagent 隨便命名成角色的名字，是沒有用的。

## 平台間的已知差異 (Codex 版降級狀況)

我不打算粉飾太平，目前 Codex 的設定檔還沒辦法做到跟 Claude Code 完全對等：

- **沒有硬性的對話回合上限**：`too-te` 在 Claude Code 端有 `maxTurns: 100` 來強制煞車，但 Codex 沒這功能，所以只能把「100 回合」寫進提示詞裡當作自我約束，系統並不會幫我們強制斷線。備案是契約裡的收尾規則：預算快見底時，它得自己找個乾淨的斷點停下來，把進度寫成 breakpoint 回報。
- **無法精準限制工具 (Tool Blocklist)**：Claude Code 可以用設定檔把角色限制為葉節點 (`too-te` 和 `sai-hu` 的 `disallowedTools: Agent, Workflow`)，或規定 `explore` 只能讀取。Codex 目前沒有這類黑名單機制。不過實測發現目前版本 spawn 出來的 subagent 本來就拿不到任何 multi-agent 工具，所以「不能再往下派工」這件事現階段其實是原生保證的；我們在 Codex 版寫明的 `[agents] enabled = false` 和文字規範，是防未來版本開放巢狀 spawn 的保險。真正只能防君子的是更細的工具限制，例如要求 `explore` 只用讀取類工具，這在 Codex 沒有對應機制。
- **沙盒權限比較粗糙**：Codex 的沙盒只有三段開關 (read-only、workspace-write、danger-full-access)，我們把 `explore` 設為唯讀，另外兩個設為寫入。這跟 Claude Code 那種可以直接限制使用特定工具的精細度比起來，還是有些落差；而且沙盒管的是檔案系統和執行權限，管不到角色實際會伸手去用哪個工具。

總結來說，這個專案提供的是基本的雙平台支援，如果你需要極致的安全性保障 (例如嚴格的強制停止或工具封鎖)，還是得根據平台當下的能力自行微調。
