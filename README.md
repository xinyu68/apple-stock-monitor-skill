# Apple Stock Monitor Skill

面向 Hermes Agent、Codex 等 Agent 的 Apple 官方到店取货库存监控 Skill。无需桌面界面，通过自然语言配置地区、城市、型号、容量和颜色；有货、持续异常及恢复时通过 Bark 推送。

## 一句话安装

把仓库发布到 GitHub 后，可以直接对支持 Agent Skills 的 Agent 说：

```text
请安装这个 skill：https://github.com/xinyu68/apple-stock-monitor-skill/tree/main/apple-stock-monitor
```

Codex：

```text
$skill-installer install https://github.com/xinyu68/apple-stock-monitor-skill/tree/main/apple-stock-monitor
```

Hermes Agent：

```bash
hermes skills install github:xinyu68/apple-stock-monitor-skill/apple-stock-monitor
```

## 使用示例

安装后直接说：

```text
配置 Bark 地址 https://api.day.app/你的Key，并测试推送。
监控北京所有门店 iPhone 18 Pro Max 银色 256 GB 的库存，每分钟检查一次。
查看 Apple 库存监控状态。
停止 beijing-18-pro-max 监控任务。
```

脚本仅使用 Python 标准库。配置默认保存在用户目录的 `.apple-stock-monitor` 中，Bark Key 不会写入仓库。

## 边界

- 查询的是 Apple 商城前端使用的官方域名接口，但它不是 Apple 承诺稳定的公开开发者 API
- 只查询和提醒，不加购、不预留、不下单
- 本机任务要求电脑保持开机并联网
- 全国范围应使用至少三分钟间隔，避免高频请求触发限制

维护与接口迁移说明见 [`apple-stock-monitor/references/maintenance.md`](apple-stock-monitor/references/maintenance.md)。
