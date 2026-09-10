# 定时任务与运行环境

仅在创建、修复或迁移定时任务时读取本文。

## 推荐策略

- 单城市、少量 SKU：每 1 分钟执行一次 `check`
- 中国大陆全部门店：至少每 3 分钟执行一次，并使用内置位置分片
- 给查询时间增加轻微抖动，避免大量实例同时访问 Apple
- 到货只在状态由非有货变为有货时推送

## 调度方式

`schedule create` 在 Windows 创建两个 Task Scheduler 任务，在 macOS/Linux 创建两条用户 crontab：

1. 库存检查任务
2. 独立 watchdog 任务

Hermes Agent 支持脚本型或 Skill 型 Cron 时，也可让 Hermes 调用 `check`；机械轮询优先使用无 Agent 模式，避免每分钟消耗模型调用。

Codex/ChatGPT 桌面定时任务需要本机保持开机且应用运行。高频库存查询优先使用脚本安装的操作系统任务，Agent 只负责配置、诊断和变更任务。

## 限制

- 本机断电、断网时，本机 watchdog 同样无法发送 Bark
- 要监控整台电脑离线，必须在另一台主机部署外部心跳检查
- Bark 服务故障时无法通过 Bark 报告 Bark 自身故障，只能写入本地状态和日志
- 任务创建成功不等于查询成功；创建前必须先运行一次 `check` 并测试 Bark

## 运维命令

```text
python scripts/apple_stock_monitor.py status
python scripts/apple_stock_monitor.py schedule remove --name beijing-18-pro-max
python scripts/apple_stock_monitor.py watchdog --max-age 5
```

更新 Skill 后重新运行同名 `schedule create`，任务会被替换为新脚本路径和参数，不要创建名称不同但条件相同的重复任务。
