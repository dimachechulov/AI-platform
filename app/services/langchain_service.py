from typing import List, Dict, Optional, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import Tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from app.core.config import settings
from app.db.database import DatabaseSession
from app.db import repositories as repo
from app.services.vector_store import vector_store
from app.core.tracing import get_callback_manager
import httpx
import json


class LangChainService:
    """Сервис для работы с LangChain и Gemini"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.7,
            convert_system_message_to_human=True,
            callback_manager=get_callback_manager(),
        )

    def _build_tool_instruction(self, tools: List[Tool]) -> str:
        """Generate instruction text describing available tools."""
        if not tools:
            return ""

        lines = [
            "TOOLS:",
            "You may call a tool by responding ONLY with strict JSON:",
            '{"action":"tool","tool_name":"<name>","arguments":{"key":"value"}}',
            "Available tools:",
        ]
        for tool in tools:
            lines.append(f"- {tool.name}: {tool.description or 'No description'}")
        lines.append(
            "If no tool is required, respond in natural language with the final answer."
        )
        return "\n".join(lines)

    def _compose_system_prompt(self, base_prompt: str, tool_instruction: str) -> str:
        base = base_prompt.strip() if base_prompt else ""
        if tool_instruction:
            if base:
                return f"{base}\n\n{tool_instruction}"
            return tool_instruction
        return base or "You are a helpful assistant."

    def _normalize_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text") or "")
                else:
                    parts.append(str(item))
            return " ".join(parts).strip()
        return ""

    def _extract_tool_calls(self, content: Any) -> List[Dict[str, Any]]:
        """Parse tool calls from model response content."""
        normalized = self._normalize_content(content)
        if not normalized:
            return []
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return []

        payloads = payload if isinstance(payload, list) else [payload]
        tool_calls = []
        for item in payloads:
            if not isinstance(item, dict):
                continue
            if item.get("action") != "tool":
                continue
            tool_name = item.get("tool_name") or item.get("name")
            if not tool_name:
                continue
            args = (
                item.get("arguments")
                or item.get("args")
                or item.get("tool_input")
                or {}
            )
            tool_calls.append(
                {
                    "id": item.get("tool_call_id") or f"call_{tool_name}",
                    "name": tool_name,
                    "arguments": args,
                }
            )
        return tool_calls
    
    def create_rag_tool(
        self,
        workspace_id: int,
        allowed_document_ids: Optional[List[int]] = None,
    ) -> Tool:
        """Создание инструмента для RAG поиска"""
        def search_documents(query: str) -> str:
            """Поиск в документах workspace"""
            documents = vector_store.search_similar_chunks(workspace_id, query, k=3)
            if allowed_document_ids:
                allowed_set = set(allowed_document_ids)
                documents = [
                    doc
                    for doc in documents
                    if (doc.metadata or {}).get("document_id") in allowed_set
                ]
            if not documents:
                return "No relevant documents found."
            
            results = []
            for doc in documents:
                metadata = doc.metadata or {}
                filename = metadata.get("filename", "unknown")
                chunk_index = metadata.get("chunk_index", "?")
                results.append(
                    f"Document: {filename} (chunk #{chunk_index})\nContent: {doc.page_content}"
                )
            
            return "\n\n---\n\n".join(results)
        
        return Tool(
            name="search_documents",
            description="Search for information in uploaded documents",
            func=search_documents
        )
    
    def create_api_tool(self, api_tool_config: dict) -> Tool:
        """Создание инструмента для вызова внешнего API"""
        def call_api(**kwargs) -> str:
            """Вызов внешнего API"""
            try:
                method = api_tool_config.get("method", "GET").upper()
                url = api_tool_config.get("url")
                headers = api_tool_config.get("headers", {}) or {}
                base_params = api_tool_config.get("params", {}) or {}
                body_schema = api_tool_config.get("body_schema", {}) or {}
                
                # Объединяем базовые параметры с параметрами из вызова
                params = {**base_params, **kwargs}
                
                if method == "GET":
                    response = httpx.get(url, headers=headers, params=params, timeout=10.0)
                elif method == "POST":
                    # Объединяем body_schema с параметрами из вызова
                    body = {**body_schema, **kwargs}
                    response = httpx.post(url, headers=headers, json=body, timeout=10.0)
                elif method == "PUT":
                    body = {**body_schema, **kwargs}
                    response = httpx.put(url, headers=headers, json=body, timeout=10.0)
                elif method == "DELETE":
                    response = httpx.delete(url, headers=headers, params=params, timeout=10.0)
                else:
                    return f"Unsupported HTTP method: {method}"
                
                response.raise_for_status()
                
                # Пытаемся вернуть JSON, если не получается - возвращаем текст
                try:
                    return json.dumps(response.json(), ensure_ascii=False)
                except:
                    return response.text
            except httpx.HTTPStatusError as e:
                return f"HTTP Error {e.response.status_code}: {e.response.text}"
            except Exception as e:
                return f"Error calling API: {str(e)}"
        
        return Tool(
            name=api_tool_config.get("name", "api_tool"),
            description=api_tool_config.get("description", "Call external API"),
            func=call_api
        )
    
    def build_graph_from_config(
        self,
        config: dict,
        system_prompt: str,
        db: DatabaseSession,
        workspace_id: int,
    ) -> StateGraph:
        """Построение LangGraph из расширенной конфигурации."""
        normalized = self._normalize_graph_config(config, system_prompt)
        nodes = {node["id"]: node for node in normalized["nodes"]}

        workflow = StateGraph(dict)
        for node_id, node_config in nodes.items():
            workflow.add_node(
                node_id,
                self._make_node_executor(node_config, workspace_id, db),
            )

        workflow.set_entry_point(normalized["entry_node_id"])

        for node_id, node_config in nodes.items():
            transitions = node_config.get("transitions", [])
            valid_targets = {
                transition["target_node_id"]
                for transition in transitions
                if transition["target_node_id"] in nodes
            }

            if not valid_targets:
                workflow.add_edge(node_id, END)
                continue

            mapping = {target: target for target in valid_targets}
            mapping["end"] = END

            workflow.add_conditional_edges(
                node_id,
                self._make_transition_selector(node_config, nodes),
                mapping,
            )

        return workflow

    async def process_message(
        self,
        message: str,
        history: List[dict],
        bot_config: dict,
        system_prompt: str,
        db: DatabaseSession,
        workspace_id: int,
    ) -> str:
        """Обработка сообщения через LangChain Graph."""
        graph = self.build_graph_from_config(bot_config, system_prompt, db, workspace_id)
        app = graph.compile()

        messages: List[Any] = []
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=message))

        result = app.invoke({"messages": messages})
        final_messages = result.get("messages", [])
        last_ai = self._get_last_ai_message(final_messages)
        last_user = self._get_last_user_message(final_messages)

        if last_ai and last_ai.content:
            return last_ai.content
        if last_user and last_user.content:
            return last_user.content
        if final_messages:
            fallback = final_messages[-1]
            if hasattr(fallback, "content"):
                return fallback.content
            return str(fallback)
        return ""

    def _normalize_graph_config(self, config: dict, default_prompt: str) -> dict:
        """Преобразует legacy-конфиг в новый формат."""
        if config.get("nodes") and config.get("entry_node_id"):
            return config

        return {
            "entry_node_id": "default",
            "nodes": [
                {
                    "id": "default",
                    "name": "Default Node",
                    "system_prompt": default_prompt,
                    "use_rag": config.get("use_rag", False),
                    "api_tool_ids": config.get("api_tool_ids", []),
                    "allowed_document_ids": [],
                    "transitions": [],
                }
            ],
        }

    def _make_node_executor(
        self,
        node_config: dict,
        workspace_id: int,
        db: DatabaseSession,
    ):
        """Создает функцию-исполнитель для узла графа."""
        tools: List[Tool] = []

        if node_config.get("use_rag"):
            tools.append(
                self.create_rag_tool(
                    workspace_id,
                    node_config.get("allowed_document_ids"),
                )
            )

        api_tool_ids = node_config.get("api_tool_ids") or []
        if api_tool_ids:
            api_tools_db = repo.get_api_tools_by_ids(
                db,
                workspace_id=workspace_id,
                tool_ids=api_tool_ids,
            )
            for api_tool_db in api_tools_db:
                api_tool_config = {
                    "name": api_tool_db["name"],
                    "description": api_tool_db.get("description"),
                    "url": api_tool_db["url"],
                    "method": api_tool_db["method"],
                    "headers": api_tool_db.get("headers") or {},
                    "params": api_tool_db.get("params") or {},
                    "body_schema": api_tool_db.get("body_schema") or {},
                }
                tools.append(self.create_api_tool(api_tool_config))

        tool_executor = ToolExecutor(tools) if tools else None
        tool_instruction = self._build_tool_instruction(tools)
        node_prompt = self._compose_system_prompt(
            node_config.get("system_prompt"),
            tool_instruction,
        )

        def node_runner(state: dict) -> dict:
            messages: List[Any] = list(state.get("messages", []))

            if node_config.get("use_rag"):
                query_text = self._extract_user_query(messages)
                rag_context = self._build_rag_context(
                    workspace_id,
                    query_text,
                    node_config.get("allowed_document_ids"),
                )
                if rag_context:
                    messages.append(
                        HumanMessage(
                            content=rag_context,
                            additional_kwargs={
                                "from_tool": True,
                                "tool_call_id": "auto_rag_context",
                            },
                        )
                    )

            while True:
                llm_messages = [SystemMessage(content=node_prompt)] + messages
                response = self.llm.invoke(llm_messages)
                tool_calls = self._extract_tool_calls(response.content)
                if tool_calls:
                    response.additional_kwargs = {
                        **getattr(response, "additional_kwargs", {}),
                        "tool_calls": tool_calls,
                    }
                    response.tool_calls = tool_calls

                messages.append(response)

                if not tool_calls or not tool_executor:
                    break

                for tool_call in tool_calls:
                    content = self._invoke_tool(tool_executor, tool_call)
                    messages.append(
                        HumanMessage(
                            content=f"Tool '{tool_call.get('name')}' replied:\n{content}",
                            additional_kwargs={
                                "from_tool": True,
                                "tool_call_id": tool_call.get("id")
                                or f"call_{tool_call.get('name')}",
                            },
                        )
                    )

            return {
                "messages": messages,
                "_last_node_id": node_config["id"],
            }

        return node_runner

    def _make_transition_selector(self, node_config: dict, nodes: Dict[str, dict]):
        """Создает функцию для выбора следующего узла."""

        def selector(state: dict) -> str:
            messages = state.get("messages", [])
            last_user = self._get_last_user_message(messages)
            last_ai = self._get_last_ai_message(messages)
            for transition in node_config.get("transitions", []):
                target_id = transition["target_node_id"]
                if target_id not in nodes:
                    continue
                if self._transition_matches(
                    transition.get("condition") or {},
                    last_user,
                    last_ai,
                ):
                    return target_id
            return "end"

        return selector

    def _transition_matches(
        self,
        condition: dict,
        last_user_message: Optional[HumanMessage],
        last_ai_message: Optional[AIMessage],
    ) -> bool:
        """Проверяет выполнение условия перехода."""
        condition_type = (condition or {}).get("type", "always")
        if condition_type == "always":
            return True
        if condition_type == "keyword":
            keyword = (condition or {}).get("value", "")
            if not keyword:
                return False
            # Сначала проверяем последнее пользовательское сообщение
            if last_user_message and keyword.lower() in (last_user_message.content or "").lower():
                return True
            # Затем fallback к последнему ответу модели
            if last_ai_message and keyword.lower() in (last_ai_message.content or "").lower():
                return True
            return False
        return False

    def _get_last_ai_message(self, messages: List[Any]) -> Optional[AIMessage]:
        """Возвращает последнее сообщение модели."""
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return message
        return None

    def _get_last_user_message(self, messages: List[Any]) -> Optional[HumanMessage]:
        """Возвращает последнее пользовательское сообщение (игнорируя ответы инструментов)."""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                if message.additional_kwargs.get("from_tool"):
                    continue
                return message
        return None

    def _invoke_tool(self, executor: ToolExecutor, tool_call: Dict[str, Any]) -> str:
        """Выполняет вызов инструмента с обработкой ошибок."""
        tool_name = (
            tool_call.get("name")
            or tool_call.get("tool_name")
            or tool_call.get("function", {}).get("name")
        )
        if not tool_name:
            return "Tool name missing"

        tool_args = (
            tool_call.get("arguments")
            or tool_call.get("args")
            or tool_call.get("function", {}).get("arguments")
            or {}
        )
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except Exception:
                tool_args = {}

        try:
            invocation = ToolInvocation(tool=tool_name, tool_input=tool_args)
            result = executor.invoke(invocation)
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"

    def _extract_user_query(self, messages: List[Any]) -> str:
        """Возвращает содержимое последнего пользовательского запроса."""
        user_msg = self._get_last_user_message(messages)
        return user_msg.content if user_msg and isinstance(user_msg.content, str) else ""

    def _build_rag_context(
        self,
        workspace_id: int,
        query: str,
        allowed_document_ids: Optional[List[int]],
        top_k: int = 3,
    ) -> str:
        """Формирует текстовый контекст из RAG результатов."""
        if not query:
            return ""

        documents = vector_store.search_similar_chunks(workspace_id, query, k=top_k)
        allowed_set = set(allowed_document_ids or [])
        results = []
        for doc in documents:
            metadata = doc.metadata or {}
            doc_id = metadata.get("document_id")
            if allowed_set and doc_id not in allowed_set:
                continue
            filename = metadata.get("filename", "unknown")
            chunk_index = metadata.get("chunk_index", "?")
            results.append(
                f"Document: {filename} (chunk #{chunk_index})\nContent: {doc.page_content}"
            )

        if not results:
            return ""

        return "RAG context:\n" + "\n\n---\n\n".join(results)


# Глобальный экземпляр
langchain_service = LangChainService()

