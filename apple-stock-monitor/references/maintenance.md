# Apple 接口原理与修复手册

仅在库存查询异常、商品无法匹配、门店缺失或维护脚本时读取本文。

## 查询链路

1. 从中国大陆 Apple iPhone 购买入口发现产品系列页面
2. 从系列页面的 `PRODUCT_SELECTION_BOOTSTRAP.productSelectionData` 解析当前商品、展示维度和零件号。个别商品名称可能重复，真正的查询键始终是 `partNumber`
3. 请求 `https://www.apple.com.cn/shop/retail/pickup-message`，参数为一个或多个 `parts.N` 和位置邮编
4. 从每家门店的 `partsAvailability` 读取 `pickupDisplay`

该接口属于 Apple 商城前端内部接口，不是承诺兼容性的公开 API。请求成功只说明当前实现有效，不代表长期稳定。

脚本先使用 Python `urllib`，遇到操作系统 TLS/代理兼容问题时自动回退到系统 `curl`。两条传输路径共享同一解析器和安全上限。

## 不变量

- HTTP 错误、非 JSON、关键字段缺失、零件号缺失全部归类为 `unknown` 或命令失败，绝不归类为无货
- `unavailable` 只能来自 Apple 明确返回的 `pickupDisplay=unavailable`
- 目录刷新失败时保留上一份有效缓存
- Bark 推送失败不能改写已经确认的库存结果
- 日志和命令输出不得包含完整 Bark Key

## 常见故障

### HTTP 541、403 或拦截页

先降低频率并确认使用 `/shop/retail/pickup-message`，不要退回已经长期返回 541 的 `/shop/fulfillment-messages`。保存状态码、响应 Content-Type、响应长度和前 200 个脱敏字符。

如果 retail 接口也要求浏览器校验，应新增独立 transport 适配器，通过隔离的 Chrome/Edge 会话获取 Apple Cookie；不要把浏览器逻辑混进库存解析器。

### 找不到商品

运行：

```text
python scripts/apple_stock_monitor.py catalog-refresh
```

检查缓存中是否仍有目标系列、容量、颜色和 `partNumber`。如果购买入口出现新 slug，修复 `discover_families`；如果 bootstrap 键变化，先搜索购买页中的 `productSelectionData`、`partNumber` 和 `dimensionColor`，再修改解析器并新增固定响应测试。

### 找不到城市或门店

先用有效邮编直接请求 pickup 接口。若 Apple 新增直营店城市，在 `CITY_POSTCODES` 增加城市中心邮编。全国查询依赖多个位置锚点并按 `storeNumber` 去重；Apple 单次只返回附近门店，不能假定一个北京邮编会返回全国门店。

### 响应结构变化

保存脱敏 JSON 为测试 fixture，依次确认：

```text
body.stores[]
storeNumber
partsAvailability[partNumber]
pickupDisplay
messageTypes.regular.storePickupQuote
```

先扩展兼容解析，再替换旧路径。至少保留一个旧结构 fixture，防止修复新结构时破坏旧结构。

## 发布前回归

- 目录刷新至少解析出一个产品和一个零件号
- 精确条件只解析出预期 SKU
- 有货、无货、未知三种 fixture 均通过
- 北京查询返回的门店城市均为北京
- 连续错误达到阈值后只发送一次错误通知
- 恢复后发送恢复通知
- Bark 到货通知携带 Apple 官方购买页 URL
- watchdog 能识别过期心跳
