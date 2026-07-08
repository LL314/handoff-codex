# handoff-codex

帮助 Codex App 自动监控会话 context，并在达到阈值时触发交接。

## 功能

- 通过 Codex `Stop` hook 读取 transcript 中的 token 统计。
- 通过 Codex `PreCompact` hook 在自动压缩前做最后兜底。
- 默认在自动压缩阈值前 `2000` tokens 触发交接。
- 提示 Codex 使用 `$handoff-codex` 生成简短交接文档。
- 默认交接目录为当前项目下的 `work/handoffs/<project-name>/`。

## 默认配置

- 默认自动压缩上限：`200000` tokens
- 默认提前量：`2000` tokens
- 默认交接阈值：`198000` tokens
- 自动压缩上限环境变量：`HANDOFF_CODEX_AUTO_COMPACT_LIMIT`
- 提前量环境变量：`HANDOFF_CODEX_MARGIN`
- 显式阈值环境变量：`HANDOFF_CODEX_THRESHOLD`
- 交接目录根路径环境变量：`HANDOFF_CODEX_DATA`
- 调试日志环境变量：`HANDOFF_CODEX_DEBUG=1`

## 安装

推荐将仓库克隆到固定路径：

```bash
mkdir -p ~/plugins
git clone https://github.com/LL314/handoff-codex.git ~/plugins/handoff-codex
```

然后在 Codex App 中启用个人插件来源，或将该路径加入你的 personal marketplace。

当前 hook 命令默认从以下路径执行脚本：

```text
~/plugins/handoff-codex/scripts/handoff_check.py
```

首次启用 hook 时，Codex App 可能要求信任该 hook；需要手动确认一次。

## 使用

手动创建交接：

```text
Use $handoff-codex to create a handoff for this session.
```

自动触发时，hook 会要求 Codex 使用 `$handoff-codex` 写交接文档，并提示你在新 Codex App 线程中粘贴恢复 prompt。

`Stop` hook 负责提前触发；`PreCompact` hook 负责在 Codex 已经准备自动压缩时阻止本次压缩。手动 compact 不会被拦截。

## 文件结构

```text
.codex-plugin/plugin.json
hooks/hooks.json
scripts/handoff_check.py
skills/handoff-codex/SKILL.md
```

## 注意

这个插件只能在 Codex App 支持插件 hooks 的环境中自动触发。普通 skill 本身不能自动监控 context；自动触发依赖 `Stop` 和 `PreCompact` hook。
