class QueryRewriter:
    """
    查询重写器，根据用户查询和记忆上下文生成多个查询变体，以覆盖不同的研究方向。
    目前的实现基于简单的关键词匹配和预定义的研究方向列表
        - 如果记忆上下文中包含与轻量化相关的关键词，则生成 "lightweight" 方向的查询变体
        - 如果记忆上下文中包含与可解释性相关的关键词，则生成 "interpretability" 方向的查询变体
        - 如果记忆上下文中包含与模块化架构相关的关键词，则生成 "modular architecture" 方向的查询变体
        - 如果记忆上下文中包含与损失函数相关的关键词，则生成 "loss function" 方向的查询变体
    如果没有匹配到任何关键词，则默认生成 "survey" 和 "recent methods" 方向的查询变体

    当前还有几个你需要知道的限制：
        advanced 现在仍是规则改写，不是真正智能体。
            memory_context 当前来自 confirmed semantic memory section 和最近 structured experiment logs。
            rewritten queries 可能产生多次外部检索；未来真实调用 arXiv/OpenAlex 时要考虑限速和去重。
            MemoryStore.build_memory_context() 当前不读取 legacy /logs，也不保存聊天历史。


    """
    def rewrite(self, mode: str, user_query: str, memory_context: str = "") -> list[str]:
        query = user_query.strip()
        if not query:
            return []

        if mode == "basic":
            return [query]

        directions: list[str] = []
        context = memory_context.lower()

        if "light" in context or "heavy" in context or "轻量" in context:
            directions.append("lightweight")
        if "interpret" in context or "可解释" in context:
            directions.append("interpretability")
        if "module" in context or "模块" in context:
            directions.append("modular architecture")
        if "loss" in context or "损失" in context:
            directions.append("loss function")

        if not directions:
            directions = ["survey", "recent methods"]

        return [query] + [f"{query} {direction}" for direction in directions[:4]]
