# Apple Stock Monitor Skill

面向 Hermes Agent、Codex 等 Agent 的 Apple 官方到店取货库存监控 Skill。无需桌面界面，通过自然语言配置地区、城市、型号、容量和颜色；有货、持续异常及恢复时通过 Bark 推送。

## 一句话安装

把仓库发布到 GitHub 后，可以直接对支持 Agent Skills 的 Agent 说：

```text
请安装这个 skill：https://github.com/xinyu68/apple-stock-monitor-skill/tree/main/apple-stock-monitor
安装完成后请立即询问我的 Bark Key 或完整 Bark URL，以便完成首次配置和测试推送；即使新 Skill 要到下一轮才生效，也要在安装结果中主动询问。
```

## 更新 Skill

需要更新时，直接对 Agent 说：

```text
请将已安装的 apple-stock-monitor 更新到这个仓库的最新版本：
https://github.com/xinyu68/apple-stock-monitor-skill/tree/main/apple-stock-monitor
如果安装器不支持覆盖，只删除并重新安装 apple-stock-monitor 的 Skill 目录；保留用户目录 .apple-stock-monitor 中的 Bark 配置和监控状态，并保留 Agent 中已有的监控任务。更新后请校验 Skill 并运行测试。
```

## 使用示例

安装器本身没有通用的“安装后自动运行”钩子。首次使用 Skill 时，Agent 会先检查 Bark 配置；如未配置，会主动向用户索要 Bark Key 或完整 URL。一次性库存查询可以继续执行，但创建定时监控前必须完成测试推送。

安装后直接说：

```text
配置 Bark 地址 https://api.day.app/你的Key，并测试推送。
监控北京所有门店 iPhone 18 Pro Max 银色 256 GB 的库存，每分钟检查一次。
查看 Apple 库存监控状态。
停止 beijing-18-pro-max 监控任务。
```

脚本仅使用 Python 标准库。配置默认保存在用户目录的 `.apple-stock-monitor` 中，Bark Key 不会写入仓库。周期运行由 Codex、Hermes 等 Agent 自带的定时任务功能负责，不创建 Windows 任务计划或系统 crontab。

同一门店、同一料号持续有货时最多每 30 分钟推送一次；如果库存先变为无货或不可自提，之后再次有货，则立即推送，不等待冷却时间。多个监控任务的提醒状态彼此不会互相清除。

## 边界

- 查询的是 Apple 商城前端使用的官方域名接口，但它不是 Apple 承诺稳定的公开开发者 API
- 只查询和提醒，不加购、不预留、不下单
- 本机型 Agent 定时任务通常要求电脑保持开机、联网且 Agent 宿主可用
- 全国范围应使用至少三分钟间隔，避免高频请求触发限制

维护与接口迁移说明见 [`apple-stock-monitor/references/maintenance.md`](apple-stock-monitor/references/maintenance.md)。
