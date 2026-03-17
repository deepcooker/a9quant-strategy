summarize-role: 请你对当前角色线程做一次去噪总结。

目标：
- 只保留对 task 层真正有价值的稳定结论
- 不复述聊天过程
- 为后续 task summary 聚合提供可直接引用的 role-level summary

要求：
- 总结当前角色线程已经完成了什么
- 识别当前角色看到的风险、阻塞或验证缺口
- 给出对 task 下一步的建议
