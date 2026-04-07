"""LangGraph Agent 节点函数"""

import logging
import time
import re
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool

from agents.services.smart_memory import SmartMemoryManager

from .state import AgentState, ExecutionStep
from agents.services.observation_masking import ObservationMasker

logger = logging.getLogger(__name__)


# ============ 表元数据配置（用于智能表选择）============

TABLE_METADATA = {
    "vehicle_info": {
        "description": "车辆基本信息表，存储车辆的静态属性",
        "keywords": ["车辆", "车型", "品牌", "注册日期", "VIN", "能源类型", "燃油", "电动", "混动"],
        "embedding": None,
    },
    "vehicle_workload": {
        "description": "车辆工况数据表，包含实时行驶工况数据、能耗、燃油消耗、速度、里程等动态数据",
        "keywords": ["能耗", "耗电", "耗油", "耗能", "电耗", "速度", "里程", "工况", "行驶", "工作时间", "加速", "减速", "功耗", "电量", "油耗"],
        "embedding": None,
    },
    "sensor_data": {
        "description": "传感器数据表，实时传感器数据包括座椅传感器、温度、湿度、GPS信号强度等信息",
        "keywords": ["座椅", "日活", "日活率", "活跃", "活活率", "温度", "湿度", "GPS", "信号强度", "传感器", "占用", "传感器激活", "座椅激活"],
        "embedding": None,
    },
    "vehicle_fault": {
        "description": "车辆故障记录表，记录车辆的故障信息包括故障码、故障类型、故障严重程度和诊断信息",
        "keywords": ["故障", "失效", "失效率", "错误", "异常", "故障码", "故障类型", "故障率", "诊断", "故障发生", "故障统计", "异常检测"],
        "embedding": None,
    }
}

# ============ 字段元数据配置（用于智能字段选择）============

FIELD_METADATA = {
    "vehicle_info": {
        "vehicle_id": {
            "description": "车辆唯一标识符",
            "type": "identifier",
            "keywords": ["车辆ID", "标识", "编号"],
        },
        "vehicle_name": {
            "description": "车辆名称，如北京EU5、特斯拉Model 3等",
            "type": "categorical",
            "keywords": ["车辆名称", "车型名称", "型号"],
        },
        "fuel_type": {
            "description": "能源类型：electric电动、hybrid混动、fuel燃油",
            "type": "categorical",
            "keywords": ["能源类型", "燃油", "电动", "混动", "新能源"],
        },
        "model": {
            "description": "年份型号，如2024、2023、2022",
            "type": "categorical",
            "keywords": ["型号", "年份", "年代"],
        },
    },
    "vehicle_workload": {
        "vehicle_id": {
            "description": "关联的车辆ID",
            "type": "identifier",
            "keywords": ["车辆ID", "关联"],
        },
        "date": {
            "description": "工况记录日期，格式YYYY-MM-DD",
            "type": "temporal",
            "keywords": ["日期", "时间", "日子"],
        },
        "distance": {
            "description": "行驶里程，单位km",
            "type": "numeric",
            "keywords": ["里程", "距离", "公里", "行驶距离"],
        },
        "power_consumption": {
            "description": "电能消耗，单位kWh（新能源车）",
            "type": "numeric",
            "keywords": ["能耗", "耗电", "电耗", "电量消耗", "功耗"],
        },
        "fuel_consumption": {
            "description": "燃油消耗，单位L（燃油车）",
            "type": "numeric",
            "keywords": ["油耗", "燃油消耗", "汽油消耗"],
        },
        "avg_speed": {
            "description": "平均速度，单位km/h",
            "type": "numeric",
            "keywords": ["平均速度", "速度", "平均"],
        },
        "max_speed": {
            "description": "最高速度，单位km/h",
            "type": "numeric",
            "keywords": ["最高速度", "最快", "最大速度"],
        },
        "idle_time": {
            "description": "怠速时间，单位分钟",
            "type": "numeric",
            "keywords": ["怠速", "停止时间", "待命"],
        },
    },
    "sensor_data": {
        "vehicle_id": {
            "description": "关联的车辆ID",
            "type": "identifier",
            "keywords": ["车辆ID"],
        },
        "date": {
            "description": "传感器数据记录日期",
            "type": "temporal",
            "keywords": ["日期", "时间"],
        },
        "seat_sensor_active": {
            "description": "座椅传感器激活状态：1=激活/有人、0=未激活/无人",
            "type": "binary",
            "keywords": ["座椅", "日活", "日活率", "激活", "活跃", "占用", "有人"],
        },
        "temperature": {
            "description": "车内温度，单位℃",
            "type": "numeric",
            "keywords": ["温度", "热度", "冷热", "摄氏度"],
        },
        "humidity": {
            "description": "车内湿度，百分比%",
            "type": "numeric",
            "keywords": ["湿度", "潮湿", "干燥"],
        },
        "gps_signal_strength": {
            "description": "GPS信号强度，单位dBm",
            "type": "numeric",
            "keywords": ["GPS", "信号强度", "信号", "位置"],
        },
    },
    "vehicle_fault": {
        "vehicle_id": {
            "description": "关联的车辆ID",
            "type": "identifier",
            "keywords": ["车辆ID"],
        },
        "date": {
            "description": "故障发生日期",
            "type": "temporal",
            "keywords": ["日期", "时间"],
        },
        "fault_code": {
            "description": "OBD故障代码，如P0300、P0401等",
            "type": "categorical",
            "keywords": ["故障码", "代码", "错误码"],
        },
        "fault_type": {
            "description": "故障类型，如engine_fault、sensor_fault、battery_fault等",
            "type": "categorical",
            "keywords": ["故障类型", "类型", "类别"],
        },
        "fault_severity": {
            "description": "故障严重程度：low/medium/high",
            "type": "categorical",
            "keywords": ["严重程度", "严重性", "等级"],
        },
        "fault_count": {
            "description": "该故障的发生次数",
            "type": "numeric",
            "keywords": ["次数", "数量", "统计", "失效率"],
        },
    }
}


class OptimizedTableSelector:
    """基于向量相似度的智能表选择器 - 快速、准确、无需LLM调用"""

    def __init__(self):
        """初始化表选择器 - 第一次调用时初始化embedding模型"""
        self.embeddings_model = None
        self.table_metadata = TABLE_METADATA
        self.query_cache = {}  # 缓存查询结果
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化embedding模型（第一次调用时）"""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Initializing sentence transformer for table selection...")
            self.embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')

            # 预计算所有表的embedding
            for table_name, meta in self.table_metadata.items():
                text = f"{meta['description']} {' '.join(meta['keywords'])}"
                meta['embedding'] = self.embeddings_model.encode(text)
                logger.info(f"✓ Precomputed embedding for table: {table_name}")

            self._initialized = True
            logger.info("✓ Table selector initialized successfully")
        except ImportError:
            logger.warning("sentence-transformers not installed, falling back to keyword matching")
            self._initialized = True

    def select_tables(self, user_input: str, clarified_terms: List[Dict]) -> List[str]:
        """选择相关的表 - 向量相似度方法"""

        self._ensure_initialized()

        # 检查缓存
        cache_key = self._hash_query(user_input + str(clarified_terms))
        if cache_key in self.query_cache:
            logger.info("🎯 Cache hit for table selection")
            return self.query_cache[cache_key]

        # 如果没有embedding模型，降级到关键字匹配
        if not self.embeddings_model:
            logger.warning("⚠️ Using fallback keyword matching")
            return self._keyword_select(user_input, clarified_terms)

        try:
            # 拼接查询文本
            query_text = user_input + " " + " ".join(
                f"{t['term']} {t['meaning']}"
                for t in clarified_terms
            )

            # 计算query embedding
            from sklearn.metrics.pairwise import cosine_similarity
            query_embedding = self.embeddings_model.encode(query_text)

            # 计算与所有表的相似度
            similarities = {}
            for table_name, meta in self.table_metadata.items():
                if meta['embedding'] is None:
                    continue
                sim = cosine_similarity(
                    [query_embedding],
                    [meta['embedding']]
                )[0][0]
                similarities[table_name] = sim

            logger.info(f"📊 Table similarities: {similarities}")

            # 选择相似度 > 0.3 的表（中文embedding模型相似度普遍较低）
            selected_tables = [
                table for table, sim in similarities.items()
                if sim > 0.3
            ]

            # 如果没有结果，或者结果只有一个但置信度低，尝试关键字匹配
            if not selected_tables:
                logger.warning("⚠️ No table with similarity > 0.3, trying keyword fallback")
                selected_tables = self._keyword_select(user_input, clarified_terms)
                # 但只返回最相关的1-2个表，避免返回所有表
                if len(selected_tables) > 2:
                    # 按相似度排序
                    sorted_tables = sorted(
                        selected_tables,
                        key=lambda t: similarities.get(t, 0),
                        reverse=True
                    )
                    selected_tables = sorted_tables[:2]
            elif len(selected_tables) == 1:
                best_score = similarities[selected_tables[0]]
                if best_score < 0.4:
                    # 置信度不够，用关键字补充
                    logger.info(f"Low confidence ({best_score:.3f}), supplementing with keyword matching")
                    keyword_selected = self._keyword_select(user_input, clarified_terms)
                    # 合并结果，但限制到3个表
                    combined = list(set(selected_tables + keyword_selected))
                    selected_tables = combined[:3]

            logger.info(f"✅ Selected tables: {selected_tables}")

            # 缓存结果
            self.query_cache[cache_key] = selected_tables

            return selected_tables

        except Exception as e:
            logger.error(f"Vector selection error: {e}, falling back to keyword matching")
            return self._keyword_select(user_input, clarified_terms)

    def _keyword_select(self, user_input: str, clarified_terms: List[Dict]) -> List[str]:
        """关键字备选方案"""
        keywords = user_input.lower()
        for term_info in clarified_terms:
            keywords += " " + term_info.get('term', '').lower()
            keywords += " " + term_info.get('meaning', '').lower()

        selected = []
        for table_name, meta in self.table_metadata.items():
            # 检查表的关键词是否在user输入中
            if any(kw.lower() in keywords for kw in meta['keywords']):
                selected.append(table_name)

        # 如果没有通过关键字匹配到，返回所有表（让LLM决策）
        return selected if selected else list(self.table_metadata.keys())

    def _hash_query(self, query: str) -> str:
        """生成查询的哈希key用于缓存"""
        return hashlib.md5(query.encode()).hexdigest()

    def clear_cache(self):
        """清空缓存"""
        self.query_cache.clear()
        logger.info("Table selector cache cleared")


# 全局单例
_table_selector = None

def get_table_selector():
    """获取全局表选择器单例"""
    global _table_selector
    if _table_selector is None:
        _table_selector = OptimizedTableSelector()
    return _table_selector


# ============ 字段选择器（基于向量相似度）============

class OptimizedFieldSelector:
    """基于向量相似度的智能字段选择器 - 减少不必要的字段采样"""

    def __init__(self):
        """初始化字段选择器"""
        self.embeddings_model = None
        self.field_metadata = FIELD_METADATA
        self.field_embeddings = {}  # {table: {field: embedding}}
        self.query_cache = {}
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化embedding模型"""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Initializing sentence transformer for field selection...")
            self.embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')

            # 预计算所有字段的embedding
            for table_name, fields in self.field_metadata.items():
                self.field_embeddings[table_name] = {}
                for field_name, field_info in fields.items():
                    text = f"{field_info['description']} {' '.join(field_info['keywords'])}"
                    self.field_embeddings[table_name][field_name] = self.embeddings_model.encode(text)
                    logger.debug(f"✓ Precomputed embedding for {table_name}.{field_name}")

            self._initialized = True
            logger.info("✓ Field selector initialized successfully")
        except ImportError:
            logger.warning("sentence-transformers not installed, falling back to type-based selection")
            self._initialized = True

    def select_fields(self, table: str, user_input: str, clarified_terms: List[Dict], top_k: int = 3) -> List[str]:
        """为指定表选择相关字段"""

        self._ensure_initialized()

        if table not in self.field_metadata:
            logger.warning(f"Table {table} not in FIELD_METADATA, returning all fields")
            return list(self.field_metadata.get(table, {}).keys())

        # 检查缓存
        cache_key = self._hash_query(f"{table}|{user_input}|{str(clarified_terms)}|{top_k}")
        if cache_key in self.query_cache:
            logger.info(f"🎯 Cache hit for field selection in {table}")
            return self.query_cache[cache_key]

        # 如果没有embedding模型，使用类型-优先级降级
        if not self.embeddings_model:
            logger.warning("⚠️ Using fallback type-based field selection")
            return self._type_based_select(table, user_input, clarified_terms, top_k)

        try:
            # 拼接查询文本
            query_text = user_input + " " + " ".join(
                f"{t['term']} {t['meaning']}"
                for t in clarified_terms
            )

            from sklearn.metrics.pairwise import cosine_similarity
            query_embedding = self.embeddings_model.encode(query_text)

            # 计算与表中所有字段的相似度
            similarities = {}
            for field_name in self.field_metadata[table].keys():
                field_embedding = self.field_embeddings[table][field_name]
                sim = cosine_similarity([query_embedding], [field_embedding])[0][0]
                similarities[field_name] = sim

            logger.debug(f"📊 Field similarities for {table}: {similarities}")

            # 选择相似度 > 0.25 的字段
            selected_fields = [
                field for field, sim in similarities.items()
                if sim > 0.25
            ]

            # 如果没有结果，选择置信度最高的top_k字段
            if not selected_fields:
                logger.warning(f"⚠️ No field with similarity > 0.25 in {table}, using top-{top_k} by score")
                sorted_fields = sorted(
                    similarities.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                selected_fields = [field for field, _ in sorted_fields[:top_k]]

            # 限制字段数量（避免过度采样）
            if len(selected_fields) > top_k:
                sorted_fields = sorted(
                    ((f, similarities[f]) for f in selected_fields),
                    key=lambda x: x[1],
                    reverse=True
                )
                selected_fields = [field for field, _ in sorted_fields[:top_k]]

            logger.info(f"✅ Selected fields for {table}: {selected_fields}")

            # 缓存结果
            self.query_cache[cache_key] = selected_fields

            return selected_fields

        except Exception as e:
            logger.error(f"Vector field selection error: {e}, falling back to type-based selection")
            return self._type_based_select(table, user_input, clarified_terms, top_k)

    def _type_based_select(self, table: str, user_input: str, clarified_terms: List[Dict], top_k: int) -> List[str]:
        """基于字段类型的备选方案 - 优先选择标识符和与查询相关的字段"""
        fields = self.field_metadata[table]
        user_text = (user_input + " " + " ".join(f"{t['term']} {t['meaning']}" for t in clarified_terms)).lower()

        # 第一优先级：标识符字段（总是需要）
        priority_fields = []
        for field_name, field_info in fields.items():
            if field_info.get('type') == 'identifier':
                priority_fields.append(field_name)

        # 第二优先级：关键词匹配的字段
        keyword_matches = []
        for field_name, field_info in fields.items():
            if field_name not in priority_fields:
                if any(kw.lower() in user_text for kw in field_info.get('keywords', [])):
                    keyword_matches.append(field_name)

        # 第三优先级：时间字段（通常需要）
        temporal_fields = []
        for field_name, field_info in fields.items():
            if field_name not in priority_fields and field_name not in keyword_matches:
                if field_info.get('type') == 'temporal':
                    temporal_fields.append(field_name)

        # 组合结果
        selected = priority_fields + keyword_matches + temporal_fields

        # 如果还是不够，添加其他字段
        if len(selected) < top_k:
            other_fields = [f for f in fields.keys() if f not in selected]
            selected.extend(other_fields[:top_k - len(selected)])

        # 限制到top_k
        selected = selected[:top_k]

        logger.info(f"Type-based field selection for {table}: {selected}")
        return selected

    def _hash_query(self, query: str) -> str:
        """生成查询的哈希key用于缓存"""
        return hashlib.md5(query.encode()).hexdigest()

    def clear_cache(self):
        """清空缓存"""
        self.query_cache.clear()
        logger.info("Field selector cache cleared")


# 全局单例
_field_selector = None

def get_field_selector():
    """获取全局字段选择器单例"""
    global _field_selector
    if _field_selector is None:
        _field_selector = OptimizedFieldSelector()
    return _field_selector


# ============ 重试策略配置 ============

class RetryConfig:
    """重试策略配置"""

    # 基础重试次数限制
    MAX_RETRIES = 3  # 改自2，允许更多重试机会

    # 不同错误类型的重试延迟（秒）
    # 用于在重试之前等待，避免频繁重复相同的错误
    RETRY_DELAYS = {
        "syntax_error": 0.0,        # SQL语法错误：无需延迟（通常是逻辑问题）
        "field_not_exists": 0.0,    # 字段不存在：无需延迟（schema已变）
        "no_results": 0.5,          # 无结果：稍微延迟后重试（可能是临时问题）
        "invalid_answer": 0.0,      # 答案无效：无需延迟
        "evaluation_failed": 1.0,   # 评测失败：延迟后重试（可能需要重新思考）
        "timeout": 2.0,             # 超时：延迟较长（但不会重试，因为是permanent_error）
        "permission_error": 0.0,    # 权限错误：不会重试
    }

    @staticmethod
    def get_retry_delay(error_diagnosis: str) -> float:
        """获取错误类型对应的重试延迟时间（秒）"""
        return RetryConfig.RETRY_DELAYS.get(error_diagnosis, 0.5)

    @staticmethod
    def should_retry(retry_count: int, error_category: str) -> bool:
        """判断是否应该重试"""
        # permanent_error不重试
        if error_category == "permanent_error":
            return False

        # retryable_logic_error和temporary_error可以重试
        return retry_count < RetryConfig.MAX_RETRIES


class NodeManager:
    """管理所有Agent节点函数"""

    def __init__(self, llm: BaseLLM, tools: List[BaseTool], memory_manager: Optional[object] = None):
        self.llm: BaseLLM = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
        self.memory_manager:SmartMemoryManager = memory_manager

        # ✅ Phase 5: bind_tools - LLM now knows about tools and outputs structured tool_calls
        self.model_with_tools = llm.bind_tools(tools)
        logger.info(f"✓ Bound {len(tools)} tools to LLM - using LangGraph ToolNode pattern")

    def process_input_node(self, state: AgentState) -> Dict[str, Any]:
        """处理用户输入"""
        logger.info(f"Processing input for user {state['user_id']}: {state['user_input']}")

        # 从记忆中检索相关上下文
        memory_context = None
        if self.memory_manager:
            try:
                memory_context = self.memory_manager.retrieve_relevant_memory(
                    query=state['user_input'],
                    top_k=5
                )
                if memory_context:
                    logger.info(f"Retrieved memory context: {memory_context[:100]}...")
            except Exception as e:
                logger.error(f"Failed to retrieve memory: {e}")

        return {
            "memory_context": memory_context,
        }

    def agent_loop_node(self, state: AgentState) -> Dict[str, Any]:
        """✅ Agent推理 - 使用model_with_tools输出structured tool_calls"""
        logger.info(f"Agent loop (using model_with_tools)")

        # 构建提示
        system_prompt = self._build_system_prompt(state)

        # 构建消息列表（使用BaseMessage格式，兼容LangGraph）
        from langchain_core.messages import HumanMessage
        messages = [
            HumanMessage(content=system_prompt),
        ] + state.get("messages", [])

        # ✅ 关键改动：使用model_with_tools替代llm.predict()
        # model_with_tools输出AIMessage with tool_calls（不是文本）
        try:
            response = self.model_with_tools.invoke(messages)
            logger.info(f"LLM response: {len(response.content) if response.content else 0} chars, "
                       f"tool_calls={len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0}")
        except Exception as e:
            logger.error(f"LLM prediction error: {e}")
            from langchain_core.messages import AIMessage
            response = AIMessage(content=f"I encountered an error: {str(e)}")

        # 记录执行步骤
        step = ExecutionStep(
            step_type="model_call",
            tool_name=None,
            tool_input=None,
            tool_output=response.content,
            timestamp=datetime.now(),
            duration=0.0
        )

        # ✅ 返回值：添加messages而非更新scratchpad
        # ToolNode会自动处理tool_calls
        return {
            "messages": state.get("messages", []) + [response],
            "execution_steps": state["execution_steps"] + [step],
        }

    def _build_system_prompt(self, state: AgentState) -> str:
        """构建系统提示 - LLM已知道可用工具（通过bind_tools）"""
        intent = state.get("intent_type", "unknown")

        if intent == "knowledge":
            clarified = state.get("clarified_terms", [])
            return f"""You are a knowledge assistant.

User question: {state['user_input']}
Clarified terms: {clarified}

Use the available tools to find relevant knowledge."""

        elif intent == "data":
            tables = state.get("relevant_tables", [])
            time_range = state.get("time_range")
            return f"""You are a data analysis assistant.

User question: {state['user_input']}
Available tables: {tables}
Time range: {time_range}

Use the available tools to query data and generate results."""

        else:
            return f"""You are a helpful assistant.
User question: {state['user_input']}

Use the available tools if needed to help answer the question."""

    def intent_detection_node(self, state: AgentState) -> Dict[str, Any]:
        """意图识别节点 - 分类用户查询为 knowledge/data/hybrid"""
        logger.info(f"Detecting intent for: {state['user_input']}")

        # 先用启发式方法快速判断（性能优先）
        user_input = state['user_input']

        # 关键词定义
        data_keywords = {"查询", "统计", "SELECT", "表", "字段", "数据库", "数据", "SQL", "昨天", "上周", "销售", "金额"}
        knowledge_keywords = {"什么是", "定义", "含义", "解释", "术语", "代表"}

        # 计算关键词匹配得分
        data_score = sum(1 for kw in data_keywords if kw in user_input)
        knowledge_score = sum(1 for kw in knowledge_keywords if kw in user_input)

        # 启发式判断
        if knowledge_score > 0 and data_score == 0:
            intent_type = "knowledge"
        elif data_score > knowledge_score:
            intent_type = "data"
        elif data_score > 0 and knowledge_score > 0:
            intent_type = "hybrid"
        else:
            # 如果启发式判断不确定，用LLM + 历史记忆
            logger.info("Heuristic detection uncertain, using LLM with memory context")
            prompt = self._build_intent_detection_prompt(state)
            try:
                response = self.llm.predict(prompt).strip().lower()
                if "knowledge" in response or "概念" in response or "定义" in response:
                    intent_type = "knowledge"
                elif "hybrid" in response or "混合" in response:
                    intent_type = "hybrid"
                else:
                    intent_type = "data"
            except Exception as e:
                logger.error(f"LLM intent detection error: {e}")
                intent_type = "data"  # 默认为数据查询

        logger.info(f"Detected intent: {intent_type} (data_score={data_score}, knowledge_score={knowledge_score})")

        return {
            "intent_type": intent_type,
        }

    def time_check_node(self, state: AgentState) -> Dict[str, Any]:
        """时间检查节点 - 检测和转换相对时间"""
        logger.info("Checking for relative time references")

        # 检查输入中是否有相对时间关键词
        time_keywords = {"昨天", "今天", "明天", "上周", "这周", "下周", "上月", "这月", "下月",
                         "近", "最近", "过去", "之前", "以后", "周年", "月份", "年"}
        has_time_ref = any(kw in state['user_input'] for kw in time_keywords)

        time_range = None
        if has_time_ref:
            # 尝试调用 convert_relative_time 工具
            time_tool = self.tool_map.get("convert_relative_time")
            if time_tool:
                try:
                    logger.info(f"Converting relative time from input: {state['user_input']}")
                    result = time_tool.run(state['user_input'])
                    # 假设result是JSON格式的 {"start_date": "...", "end_date": "..."}
                    import json
                    try:
                        time_range = json.loads(result)
                    except:
                        time_range = {"raw_result": result}
                except Exception as e:
                    logger.warning(f"Time conversion failed: {e}")

        return {
            "time_range": time_range,
        }

    def schema_discovery_node(self, state: AgentState) -> Dict[str, Any]:
        """架构发现节点 - 使用向量相似度选择相关的表和字段"""
        logger.info("Discovering relevant tables and fields")

        # 获取 schema_query 工具
        schema_tool = self.tool_map.get("schema_query")
        if not schema_tool:
            logger.warning("schema_query tool not found")
            return {"relevant_tables": [], "relevant_fields": {}}

        try:
            # 获取澄清的术语
            clarified_terms = state.get('clarified_terms', [])

            # ========== 改进：使用向量相似度选择表 ==========
            table_selector = get_table_selector()
            relevant_tables = table_selector.select_tables(
                state['user_input'],
                clarified_terms
            )

            logger.info(f"✅ Selected tables using vector similarity: {relevant_tables}")

            # 如果没有选到表，降级获取所有表并用关键字匹配
            if not relevant_tables:
                logger.warning("No tables selected by vector similarity, falling back to all tables")
                tables_result = schema_tool.run("tables")
                all_tables = []
                if tables_result:
                    for line in tables_result.split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            table_name = line[2:].strip()
                            if table_name:
                                all_tables.append(table_name)
                relevant_tables = all_tables if all_tables else []

            # 对于每个相关的表，获取其字段信息
            relevant_fields = {}
            for table in relevant_tables:
                try:
                    fields_result = schema_tool.run(table)
                    # 解析字段结果（格式：表 'table' 的字段信息:\n- col1: type1 (NULL)\n- col2: type2 (NOT NULL)）
                    fields = []
                    for line in fields_result.split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            # 提取字段名（在 ':' 前）
                            field_part = line[2:].split(':')[0].strip()
                            if field_part:
                                fields.append(field_part)
                    relevant_fields[table] = fields
                    logger.info(f"✓ Got {len(fields)} fields from table '{table}': {fields}")
                except Exception as e:
                    logger.warning(f"Failed to get fields for {table}: {e}")

            logger.info(f"✅ Discovered tables: {relevant_tables}, fields count: {sum(len(f) for f in relevant_fields.values())}")

            return {
                "relevant_tables": relevant_tables,
                "relevant_fields": relevant_fields,
            }

        except Exception as e:
            logger.error(f"Schema discovery error: {e}")
            return {"relevant_tables": [], "relevant_fields": {}}

    def field_probing_node(self, state: AgentState) -> Dict[str, Any]:
        """字段探测节点 - 智能选择字段后采样其值，参考历史访问偏好"""
        logger.info("Probing field values with intelligent field selection")

        field_samples = {}
        sql_tool = self.tool_map.get("sql_query")

        if not sql_tool or not state.get("relevant_tables"):
            logger.info("No tables to probe")
            return {"field_samples": field_samples}

        try:
            # 获取历史记忆和澄清的术语
            memory_context = state.get("memory_context", "") or ""
            clarified_terms = state.get("clarified_terms", [])
            user_input = state.get("user_input", "")

            memory_hint = f"用户历史倾向：{memory_context[:200]}" if memory_context else "首次查询"
            logger.info(f"Field probing hint from memory: {memory_hint}")

            # 获取字段选择器
            field_selector = get_field_selector()

            # 对每个相关表执行智能字段选择
            for table in state.get("relevant_tables", []):
                try:
                    # 使用向量相似度选择最相关的字段（最多3个）
                    selected_fields = field_selector.select_fields(
                        table=table,
                        user_input=user_input,
                        clarified_terms=clarified_terms,
                        top_k=3
                    )

                    logger.info(f"Selected {len(selected_fields)} fields from {table}: {selected_fields}")

                    # 采样选中的字段
                    for field in selected_fields:
                        try:
                            # 构建探测SQL
                            probe_sql = f"SELECT DISTINCT {field} FROM {table} LIMIT 10"
                            logger.info(f"Probing: {probe_sql}")

                            result = sql_tool.run(probe_sql)
                            field_samples[f"{table}.{field}"] = result

                        except Exception as e:
                            logger.warning(f"Failed to probe {table}.{field}: {e}")
                            # 继续探测其他字段

                except Exception as e:
                    logger.error(f"Field selection error for {table}: {e}")
                    # 降级：如果字段选择失败，采样该表的所有字段
                    if table in FIELD_METADATA:
                        for field in list(FIELD_METADATA[table].keys())[:3]:
                            try:
                                probe_sql = f"SELECT DISTINCT {field} FROM {table} LIMIT 10"
                                result = sql_tool.run(probe_sql)
                                field_samples[f"{table}.{field}"] = result
                            except Exception as e2:
                                logger.warning(f"Fallback probe failed for {table}.{field}: {e2}")

            logger.info(f"Collected {len(field_samples)} field samples")

            return {
                "field_samples": field_samples,
            }

        except Exception as e:
            logger.error(f"Field probing error: {e}")
            return {"field_samples": field_samples}

    def terminology_clarification_node(self, state: AgentState) -> Dict[str, Any]:
        """术语澄清节点 - 使用RAG + 历史记忆理解用户术语（并发查询）"""
        logger.info("Clarifying terminology with memory context")

        clarified_terms = []
        doc_search_tool = self.tool_map.get("document_search")

        if not doc_search_tool:
            logger.warning("document_search tool not found")
            return {"clarified_terms": clarified_terms}

        # 使用历史记忆增强术语提取
        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户的历史术语使用】\n{memory_context}" if memory_context else ""

        # 用LLM从用户输入中提取可能需要澄清的关键术语
        extract_prompt = f"""从用户问题中提取所有可能需要澄清的关键术语和业务概念。
这些术语可能是：
- 中文业务术语（如"销售额"、"毛利率"）
- 代码或缩写（如"A厂商"、"SKU"）
- 状态值（如"已完成"、"待审核"）

用户问题: {state['user_input']}{memory_hint}

只返回一个逗号分隔的术语列表，不要解释。如果没有需要澄清的术语，返回空。"""

        try:
            # 调用LLM提取术语
            response = self.llm.predict(extract_prompt).strip()
            if not response:
                logger.info("No terms need clarification")
                return {"clarified_terms": clarified_terms}

            # 解析返回的术语列表
            terms = [t.strip() for t in response.split(',') if t.strip()]
            logger.info(f"Extracted terms for clarification: {terms}")

            # 根据意图类型选择文档分类过滤
            intent_type = state.get("intent_type", "data")
            if intent_type == "knowledge":
                # 知识路径：只查询公开文档
                doc_category = "user"
                logger.info("Using 'user' doc_category for knowledge path")
            else:
                # 数据路径/混合路径：查询内部文档（表结构、字段说明等）
                doc_category = "internal"
                logger.info("Using 'internal' doc_category for data/hybrid path")

            # 并发查询术语（最多5个）
            import concurrent.futures

            def search_term(term):
                """为单个术语查询知识库"""
                try:
                    logger.info(f"Searching knowledge base for term: {term} (category={doc_category})")
                    result = doc_search_tool.run(term, doc_category=doc_category)
                    if result:
                        logger.info(f"Found clarification for '{term}'")
                        return {"term": term, "meaning": result}
                    else:
                        logger.info(f"No RAG result for '{term}'")
                        return None
                except Exception as e:
                    logger.warning(f"Failed to clarify '{term}': {e}")
                    return None

            # 使用线程池并发查询
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(search_term, term) for term in terms[:5]]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        clarified_terms.append(result)

        except Exception as e:
            logger.error(f"Terminology clarification error: {e}")

        logger.info(f"Clarified {len(clarified_terms)} terms (concurrent)")

        return {
            "clarified_terms": clarified_terms,
        }

    def main_query_node(self, state: AgentState) -> Dict[str, Any]:
        """主查询节点 - 基于所有信息用LLM生成和执行SQL"""
        logger.info(f"Executing main query (retry_count={state.get('retry_count', 0)})")

        sql_tool = self.tool_map.get("sql_query")
        if not sql_tool:
            logger.warning("sql_query tool not found")
            return {
                "sql_result": None,
                "error_message": "SQL tool not available"
            }

        # 构建包含所有上下文的SQL生成提示
        schema_info = "\n".join([
            f"表 '{table}': 字段 {fields}"
            for table, fields in state.get("relevant_fields", {}).items()
        ])

        field_samples_info = "\n".join([
            f"- {field}: {samples}"
            for field, samples in state.get("field_samples", {}).items()
        ])

        clarified_terms_info = "\n".join([
            f"- {term_dict['term']}: {term_dict['meaning']}"
            for term_dict in state.get("clarified_terms", [])
        ])

        # 从历史记忆中提取SQL示例
        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户历史查询风格】\n{memory_context[:300]}" if memory_context else ""

        # 如果是重试，包含之前的错误信息
        retry_hint = ""
        if state.get("retry_count", 0) > 0 and state.get("error_message"):
            retry_hint = f"\n\n【之前的错误】\n{state['error_message'][:200]}\n请生成不同的SQL来避免这个错误。"

        sql_generation_prompt = f"""基于以下信息生成准确的SQL查询：

用户需求: {state['user_input']}

【澄清的术语】(来自知识库/RAG的定义和映射)
{clarified_terms_info if clarified_terms_info else "无"}

【表结构】
{schema_info if schema_info else "无相关表"}

【字段采样值】(这些是实际存在的数据)
{field_samples_info if field_samples_info else "无采样值"}

【时间范围】
{state.get('time_range', '无时间限制')}{memory_hint}{retry_hint}

SQL生成要求：
✓ 明确指定SELECT的字段，禁止SELECT *
✓ 字符串值必须加引号，时间值用YYYY-MM-DD HH:MM:SS格式
✓ 根据澄清术语中的代号、泛化语义正确指定值
✓ 根据采样值确认值格式（包括后缀、大小写、符号等）
✓ 优先使用澄清术语中确定的字段名和值映射
✓ 字段值必须从采样值或澄清术语中选择，不要造出数据库中不存在的值
✓ 只返回SQL语句，不要其他内容

生成的SQL:"""

        try:
            # 调用LLM生成SQL
            logger.info("Generating SQL with LLM")
            sql_query = self.llm.predict(sql_generation_prompt).strip()

            if not sql_query:
                logger.warning("LLM generated empty SQL")
                return {
                    "sql_result": "❌ LLM未生成SQL",
                    "error_message": "LLM generation failed"
                }

            logger.info(f"Generated SQL: {sql_query[:100]}...")

            # 执行SQL
            logger.info(f"Executing SQL: {sql_query[:100]}...")
            result = sql_tool.run(sql_query)

            return {
                "sql_result": result,
            }
        except Exception as e:
            logger.error(f"SQL generation or execution error: {e}")
            return {
                "sql_result": f"❌ SQL执行失败: {str(e)}",
                "error_message": str(e)
            }

    def result_explanation_node(self, state: AgentState) -> Dict[str, Any]:
        """结果解释节点 - 支持知识路径和数据路径的两种解释模式"""
        logger.info(f"Explaining result (intent={state.get('intent_type')})")

        intent_type = state.get('intent_type', 'data')

        # 知识路径：使用clarified_terms生成知识解释
        if intent_type == "knowledge" or not state.get("sql_result"):
            if state.get("clarified_terms"):
                prompt = self._build_knowledge_explanation_prompt(state)
                logger.info("Using knowledge explanation mode")
            else:
                return {
                    "explanation": "No clarified terms found",
                    "final_answer": "Unable to provide explanation",
                }
        # 数据路径：使用sql_result生成数据解释
        else:
            if state.get("sql_result"):
                prompt = self._build_explanation_prompt(state)
                logger.info("Using data explanation mode")
            else:
                return {
                    "explanation": "No query result found",
                    "final_answer": "Unable to provide explanation",
                }

        try:
            explanation = self.llm.predict(prompt)
        except Exception as e:
            logger.error(f"Explanation generation error: {e}")
            if state.get("sql_result"):
                explanation = f"Result: {state.get('sql_result', '')}"
            elif state.get("clarified_terms"):
                explanation = str(state.get('clarified_terms', []))
            else:
                explanation = "Failed to generate explanation"

        return {
            "explanation": explanation,
            "final_answer": explanation,  # 设置最终答案
        }


    def evaluate_node(self, state: AgentState) -> Dict[str, Any]:
        """评测执行结果 - 按路径类型分别评测，返回诊断信息供重试决策使用"""
        logger.info("Evaluating execution result")

        try:
            from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

            # 直接使用state作为execution对象（不需要Mock）
            # state中已包含所有必要的字段
            class StateExecution:
                """适配器：将AgentState转换为RuleBasedEvaluator期望的接口"""
                def __init__(self, state):
                    self.user_input = state.get("user_input", "")
                    self.agent_output = state.get("final_answer", "")
                    self.tools_used = state.get("tools_used", [])

            execution = StateExecution(state)

            # 构建测试用例（从user_input提取关键词）
            keywords = self._extract_keywords_from_input(state["user_input"])
            intent_type = state.get("intent_type", "data")

            # ========== 改进：按路径类型分开评测标准 ==========
            # 知识路径 vs 数据路径的通过标准和权重完全不同
            if intent_type == "knowledge":
                # 知识路径：只需查到相关文档，答案可以简洁
                test_case = {
                    "expected": {
                        "keywords": keywords,
                        "min_length": 5,
                        "max_length": 2000,
                        "should_NOT_contain": [],
                        "expected_tools": [],
                    }
                }
                # 知识路径用较低的通过阈值：65%（因为相关度就够了）
                pass_threshold = 0.65
            else:
                # 数据路径（data/hybrid）：需要准确的SQL查询结果
                test_case = {
                    "expected": {
                        "keywords": keywords,
                        "min_length": 10,
                        "max_length": 5000,
                        "should_NOT_contain": [],
                        "expected_tools": state.get("tools_used", []),
                    }
                }
                # 数据路径用标准阈值：75%（因为需要准确性）
                pass_threshold = 0.75

            # 调用RuleBasedEvaluator
            evaluator = RuleBasedEvaluator()
            eval_result = evaluator.evaluate(execution, test_case)

            # 提取评测结果
            eval_score = eval_result.get("score", 0.0)

            # ========== 改进：不再用eval_passed，而是用诊断信息和分数双重判断 ==========
            # eval_passed只表示规则通过，重试决策由_route_on_evaluation负责

            logger.info(f"Evaluation: score={eval_score:.2f}, threshold={pass_threshold}, intent_type={intent_type}")

            # ========== 错误诊断逻辑 ==========
            # 根据分数和诊断信息来判断是否需要诊断
            error_diagnosis = None
            error_category = None  # "retryable_logic_error" / "permanent_error" / "temporary_error"
            error_message = state.get("error_message", "")
            sql_result = state.get("sql_result")
            final_answer = state.get("final_answer", "")

            # 只在分数不够时才进行错误诊断
            if eval_score < pass_threshold:
                # 根据不同的失败症状诊断错误类型
                if error_message:
                    if any(keyword in error_message for keyword in ["语法", "syntax", "SQL", "错误的列"]):
                        error_diagnosis = "syntax_error"
                        error_category = "retryable_logic_error"
                        logger.info("Diagnosed: syntax_error (retryable)")
                    elif any(keyword in error_message for keyword in ["字段", "column", "not exist"]):
                        error_diagnosis = "field_not_exists"
                        error_category = "retryable_logic_error"
                        logger.info("Diagnosed: field_not_exists (retryable)")
                    elif any(keyword in error_message for keyword in ["超时", "timeout", "Time out"]):
                        error_diagnosis = "timeout"
                        error_category = "permanent_error"  # 工具层已重试，不需在node层再重试
                        logger.info("Diagnosed: timeout (permanent - already retried at tool layer)")
                    elif any(keyword in error_message for keyword in ["权限", "permission", "denied", "access"]):
                        error_diagnosis = "permission_error"
                        error_category = "permanent_error"
                        logger.info("Diagnosed: permission_error (permanent)")
                    else:
                        error_diagnosis = "unknown_error"
                        error_category = "permanent_error"
                elif not sql_result or (isinstance(sql_result, str) and not sql_result.strip()):
                    # SQL执行但无结果
                    error_diagnosis = "no_results"
                    error_category = "retryable_logic_error"
                    logger.info("Diagnosed: no_results (retryable)")
                elif not final_answer or len(final_answer.strip()) < 10:
                    # 最终答案太短或为空
                    error_diagnosis = "invalid_answer"
                    error_category = "retryable_logic_error"
                    logger.info("Diagnosed: invalid_answer (retryable)")
                else:
                    error_diagnosis = "evaluation_failed"
                    error_category = "retryable_logic_error"
                    logger.info("Diagnosed: evaluation_failed (retryable)")

            return {
                "evaluation_result": eval_result,
                "eval_score": eval_score,
                "error_diagnosis": error_diagnosis,
                "error_category": error_category,
            }

        except ImportError:
            logger.warning("RuleBasedEvaluator not available, using default evaluation")
            # 如果evaluator不可用，使用简单的默认评测
            final_answer = state.get("final_answer", "")
            is_valid = len(final_answer) > 10 and len(final_answer) < 5000

            return {
                "evaluation_result": {"score": 0.8 if is_valid else 0.3, "passed": is_valid},
                "eval_score": 0.8 if is_valid else 0.3,
                "error_diagnosis": None,
                "error_category": None,
            }
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            # 评测失败时返回低分
            return {
                "evaluation_result": {"score": 0.0, "passed": False},
                "eval_score": 0.0,
                "error_diagnosis": "evaluation_exception",
                "error_category": "permanent_error",
            }

    @staticmethod
    def _extract_keywords_from_input(user_input: str) -> list:
        """从用户输入中提取关键词"""
        import re
        # 简单的关键词提取：长度>2的中文词或英文词
        words = re.findall(r'[\u4e00-\u9fff]{2,}|\b[a-z]{3,}\b', user_input.lower())
        return list(set(words))[:5]  # 最多5个唯一关键词

    def error_recovery_node(self, state: AgentState) -> Dict[str, Any]:
        """错误恢复节点 - 基于错误诊断决定重试策略和延迟"""
        logger.info("Error recovery in progress")

        retry_count = state.get("retry_count", 0)
        error_diagnosis = state.get("error_diagnosis")
        error_message = state.get("error_message", "")
        intent_type = state.get("intent_type")
        error_category = state.get("error_category")

        logger.info(f"Recovery: attempt {retry_count + 1}, diagnosis={error_diagnosis}, intent={intent_type}, error: {(error_message or '')[:50]}")

        # 最多重试MAX_RETRIES次
        if retry_count >= RetryConfig.MAX_RETRIES:
            logger.warning(f"Max retry attempts ({RetryConfig.MAX_RETRIES}) reached, giving up")
            return {
                "retry_count": retry_count + 1,
                "retry_strategy": "give_up",
            }

        # 根据错误诊断添加重试延迟（在进入重试前等待一段时间）
        retry_delay = RetryConfig.get_retry_delay(error_diagnosis)
        if retry_delay > 0:
            logger.info(f"Waiting {retry_delay}s before retry to avoid repeated failures")
            time.sleep(retry_delay)

        # 根据路径类型和诊断决定重试策略
        strategy = "give_up"  # 默认放弃

        # 知识路径的重试策略
        if intent_type == "knowledge":
            if error_diagnosis == "invalid_answer":
                # 答案无效：重新查询知识库
                strategy = "requery_knowledge"
                logger.info("Strategy: requery knowledge due to invalid answer")
            elif error_diagnosis == "evaluation_failed":
                # 评测失败：重新查询知识库
                strategy = "requery_knowledge"
                logger.info("Strategy: requery knowledge due to evaluation failure")
            elif error_diagnosis == "timeout":
                # 超时：不重试
                strategy = "give_up"
                logger.info("Strategy: give up due to timeout")
            else:
                # 其他错误类型也尝试重新查询
                strategy = "requery_knowledge"
                logger.info(f"Strategy: requery knowledge (default for diagnosis={error_diagnosis})")

        # 数据路径的重试策略
        elif intent_type in ("data", "hybrid"):
            if error_diagnosis == "syntax_error":
                # SQL语法错误：重新生成SQL
                strategy = "regenerate_sql"
                logger.info("Strategy: regenerate SQL due to syntax error")
            elif error_diagnosis == "no_results":
                # 查询无结果：可能字段值采样不准，重新探测
                strategy = "reprobe_fields"
                logger.info("Strategy: reprobe fields due to no results")
            elif error_diagnosis == "field_not_exists":
                # 字段不存在：重新发现schema
                strategy = "rediscover_schema"
                logger.info("Strategy: rediscover schema due to field not exists")
            elif error_diagnosis == "timeout":
                # 超时：放弃重试
                strategy = "give_up"
                logger.info("Strategy: give up due to timeout")
            elif error_diagnosis == "invalid_answer":
                # 最终答案无效：重新生成SQL
                strategy = "regenerate_sql"
                logger.info("Strategy: regenerate SQL due to invalid answer")
            else:
                # 其他诊断：默认尝试重新生成SQL
                strategy = "regenerate_sql"
                logger.info(f"Strategy: regenerate SQL (default for diagnosis={error_diagnosis})")
        else:
            # 意图类型未知：放弃重试
            logger.warning(f"Unknown intent_type: {intent_type}, giving up")
            strategy = "give_up"

        return {
            "retry_count": retry_count + 1,
            "retry_strategy": strategy,
            "error_diagnosis": error_diagnosis,  # 保留诊断信息
        }

    def final_answer_node(self, state: AgentState) -> Dict[str, Any]:
        """生成最终答案，并将会话保存到数据库"""
        logger.info("Generating final answer and saving to memory database")

        # 获取最终答案：从explanation或sql_result
        final_answer = state.get("explanation") or state.get("sql_result") or "No answer generated"

        # 计算总时长
        end_time = datetime.now()
        duration = (end_time - state["start_time"]).total_seconds() if state["start_time"] else 0.0

        # 将本轮对话添加到记忆系统并保存到数据库
        if self.memory_manager:
            try:
                # 添加用户查询
                self.memory_manager.add_message(
                    content=state['user_input'],
                    message_type="human",
                    timestamp=state.get("start_time")
                )
                # 添加AI回答
                self.memory_manager.add_message(
                    content=final_answer,
                    message_type="ai",
                    timestamp=end_time
                )
                # 保存到数据库
                self.memory_manager.save_to_db()
                logger.info("✓ Saved conversation to memory database")
            except Exception as e:
                logger.warning(f"Failed to save to memory database: {e}")

        return {
            "final_answer": final_answer,
            "end_time": end_time,
            "total_duration": duration,
        }

    def error_handler_node(self, state: AgentState) -> Dict[str, Any]:
        """错误处理，记录失败的对话到数据库"""
        logger.error(f"Error in execution: {state.get('error_message')}")

        error_message = f"Error: {state.get('error_message', 'Unknown error')}"

        # 即使出错也记录到数据库（便于后续诊断）
        if self.memory_manager:
            try:
                self.memory_manager.add_message(
                    content=state['user_input'],
                    message_type="human",
                    timestamp=state.get("start_time")
                )
                self.memory_manager.add_message(
                    content=error_message,
                    message_type="ai",
                    timestamp=datetime.now()
                )
                self.memory_manager.save_to_db()
                logger.info("✓ Logged error conversation to memory database")
            except Exception as e:
                logger.warning(f"Failed to log error to memory database: {e}")

        return {
            "final_answer": error_message,
            "error_message": state.get("error_message"),
        }

    # ============ 辅助方法 ============

    def _build_intent_detection_prompt(self, state: AgentState) -> str:
        """构建意图识别提示词 - 使用历史记忆帮助ambiguous查询"""
        memory_context = state.get("memory_context", "") or ""
        memory_str = f"\n\n【历史相似查询】\n{memory_context}" if memory_context else ""

        prompt = f"""根据用户查询和历史对话，分类查询类型（只返回一个词）：

- knowledge: 纯知识问题（概念、术语、规则解释）
- data: 数据查询问题（涉及数据库、SQL、统计）
- hybrid: 既需要知识澄清又需要数据查询{memory_str}

当前问题: {state['user_input']}

返回: knowledge / data / hybrid"""
        return prompt

    def _build_explanation_prompt(self, state: AgentState) -> str:
        """构建结果解释提示词 - 参考历史风格"""
        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户历史回复风格】\n{memory_context[:250]}" if memory_context else ""

        prompt = f"""基于以下信息，用自然语言解释查询结果：

用户问题: {state['user_input']}

查询结果: {state.get('sql_result', 'No result')}

时间范围: {state.get('time_range', 'N/A')}

澄清的术语: {state.get('clarified_terms', [])}{memory_hint}

请用中文总结：
1. 查询理解 - 用户问题的核心
2. 关键数据 - 最重要的数值或统计
3. 业务解释 - 这些数据的含义

简洁回答，不超过200字："""
        return prompt

    def _build_knowledge_explanation_prompt(self, state: AgentState) -> str:
        """构建知识解释提示词 - 知识路径使用，参考历史风格"""
        clarified_terms_str = "\n".join([
            f"- {term['term']}: {term['meaning']}"
            for term in state.get('clarified_terms', [])
        ])

        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户历史回复偏好】\n{memory_context[:250]}" if memory_context else ""

        prompt = f"""基于以下澄清的术语和定义，用自然语言回答用户问题：

用户问题: {state['user_input']}

【已澄清的术语定义】
{clarified_terms_str or "无额外定义"}{memory_hint}

请用中文回答，包括：
1. 问题理解 - 澄清用户问题涉及的核心概念
2. 术语解释 - 相关术语的定义和含义
3. 综合答案 - 基于澄清结果的完整回答

简洁回答，不超过200字："""
        return prompt

    def _build_prompt(self, state: AgentState) -> str:
        """构建Agent提示词"""
        tools_str = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

        prompt = f"""You are a helpful AI assistant.

User input: {state['user_input']}

Tools available:
{tools_str}

Thought process:
{state['agent_scratchpad']}

Next action:"""
        return prompt

