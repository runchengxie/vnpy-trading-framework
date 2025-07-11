# 待完成功能

## 第一部分：策略开发与历史回测

此阶段的核心是利用历史数据（推荐使用高频数据，如15分钟线）来开发和验证核心交易逻辑。

- **[ ] 1. 策略选择与实现：**

- **[ ] 2. 策略分析与优化：**
  - **[ ] 参数实验：** 对策略中的关键参数（如均线周期、比率阈值、时间窗口）进行实验，评估其对策略效果的影响。
  - **[ ] 撰写数学描述：** 为选择的所有指标提供完整、清晰的数学定义和计算方法。
  - **[ ] 市场环境分析：** 讨论或通过回测数据分析，不同的市场状况（如高波动性、趋势中的跳跃）对你的策略收益有何影响。

- **[ ] 3. 技术准备：**
  - **[ ] 搭建回测环境：** 使用Python（可参考 `Backtrader`, `Zipline` 等库）。
  - **[ ] 获取数据：** 从可靠来源（如 `OpenBB` 或券商）获取高频历史数据。

## Part II：对接券商API与模拟交易

此阶段的目标是将第一部分开发的策略与券商的API连接，进行模拟交易测试。

- **[ ] 1. API功能实现：**
  - **[ ] 实现订单处理功能：**
    - **[ ]** 编写代码，通过API发送、修改和取消订单。
    - **[ ]** 明确并使用适合你策略的订单类型（如市价单、限价单）。
    - **[ ]** **安全措施：** 在测试中，设置远离当前市场价的订单参数，以防意外成交。
  - **[ ] 实现数据获取功能：**
    - **[ ]** 通过API获取实时市场数据（如果API支持）。
    - **[ ]** 通过API获取账户信息、持仓状态和历史订单。

- **[ ] 2. 整合策略与API：**
  - **[ ] 编写主交易循环：** 创建一个循环脚本，该脚本能：
    - **[ ]** 检查交易信号。
    - **[ ]** 当信号出现时，通过API执行买入/卖出操作。
    - **[ ]** 持续监控订单状态和持仓。

## Part III：风险管理与系统健壮性测试

此阶段专注于提升交易系统的稳定性和安全性，确保在真实（模拟）环境中能稳健运行。

- **[ ] 1. 实现异常处理与验证机制：**
  - **[ ] 订单状态验证：**
    - **[ ]** 检查从券商返回的订单确认信息，处理订单被拒绝、被取消、部分成交或返回信息不一致等情况。
  - **[ ] 仓位二次确认：**
    - **[ ]** 定期通过API请求账户和持仓信息，与本地记录进行比对，作为一层额外的验证。
  - **[ ] 市场数据一致性检查：**
    - **[ ]** 对接收到的市场数据进行简单的合理性检查（例如，期货价格不应低于现货价格）。

- **[ ] 2. 实现性能与风险监控：**
  - **[ ] 开发报告功能：** 创建一个简单的性能和风险报告。
  - **[ ] 计算关键风险指标：**
    - **[ ]** 跟踪和计算 **交易成本/频率 (Turnover/Costs)**。
    - **[ ]** 计算 **最大回撤 (Drawdowns)**。
    - **[ ]** 实现 **滚动VaR (Value at Risk)** 来动态评估市场风险。
