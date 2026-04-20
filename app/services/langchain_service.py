from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, Tool
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, EmailStr, Field, create_model

from app.core.config import settings
from app.db.database import DatabaseSession
from app.db.api_tool_repository import ApiToolRepository
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)
api_tool_repo = ApiToolRepository()


class ApiToolArgsSchema(BaseModel):
    """Произвольные поля тела/параметров API-инструмента."""

    model_config = ConfigDict(extra="allow")


def _aggregate_usage_from_messages(messages: List[Any]) -> Dict[str, Any]:
    """Сумма input/output по всем AIMessage; model — с последнего сообщения с model_name."""
    total_in = 0
    total_out = 0
    model: Optional[str] = None
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        um = msg.usage_metadata or {}
        if isinstance(um.get("input_tokens"), int):
            total_in += um["input_tokens"]
        if isinstance(um.get("output_tokens"), int):
            total_out += um["output_tokens"]
        rm = msg.response_metadata or {}
        if rm.get("model_name"):
            model = str(rm["model_name"])
    out: Dict[str, Any] = {}
    if total_in:
        out["input_tokens"] = total_in
    if total_out:
        out["output_tokens"] = total_out
    if model:
        out["model"] = model
    return out


def _text_from_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return " ".join(parts).strip()
    return str(content).strip()


def _tool_calls_from_ai_message(msg: AIMessage) -> List[Dict[str, Any]]:
    """Нативные tool_calls от провайдера (bind_tools)."""
    raw = getattr(msg, "tool_calls", None) or []
    out: List[Dict[str, Any]] = []
    for tc in raw:
        if isinstance(tc, dict):
            name = tc.get("name") or ""
            args = tc.get("args")
            tid = tc.get("id") or f"call_{name}"
            if name:
                out.append({"name": name, "args": args, "id": tid})
        else:
            name = getattr(tc, "name", "") or ""
            args = getattr(tc, "args", None)
            tid = getattr(tc, "id", None) or f"call_{name}"
            if name:
                out.append({"name": name, "args": args, "id": tid})
    return out


class LangChainService:
    """Gemini + LangGraph: инструменты через bind_tools и ToolMessage (без JSON-парсинга ответов)."""

    def __init__(self) -> None:
        self._llm_by_model: Dict[str, ChatGoogleGenerativeAI] = {}

    def _get_llm(self, model_name: str) -> ChatGoogleGenerativeAI:
        if model_name not in self._llm_by_model:
            self._llm_by_model[model_name] = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.7,
                convert_system_message_to_human=True,
            )
        return self._llm_by_model[model_name]

    @staticmethod
    def _optional_gemini_model(raw: Any) -> Optional[str]:
        if raw is None:
            return None
        s = str(raw).strip()
        return s or None

    def _compose_system_prompt(self, base_prompt: str, *, has_tools: bool) -> str:
        base = (base_prompt or "").strip()
        if not base:
            base = "You are a helpful assistant."
        if has_tools:
            base += (
                "\n\n**YOU NEED ALWAYS USE** provided tools"
            )
        return base

    def create_rag_tool(
        self,
        workspace_id: int,
        allowed_document_ids: Optional[List[int]] = None,
    ) -> StructuredTool:
        def search_documents(query: str) -> str:
            if not isinstance(query, str):
                query = str(query) if query else ""
            if not query.strip():
                return "Please provide a search query."

            documents = vector_store.search_similar_chunks(workspace_id, query, k=3)
            if allowed_document_ids:
                allowed_set = set(allowed_document_ids)

                def _doc_id(meta: dict) -> Optional[int]:
                    raw = meta.get("document_id")
                    if raw is None:
                        return None
                    try:
                        return int(raw)
                    except (TypeError, ValueError):
                        return None

                documents = [doc for doc in documents if _doc_id(doc.metadata or {}) in allowed_set]
            if not documents:
                return "No relevant documents found."

            blocks = []
            for doc in documents:
                metadata = doc.metadata or {}
                filename = metadata.get("filename", "unknown")
                chunk_index = metadata.get("chunk_index", "?")
                blocks.append(
                    f"Document: {filename} (chunk #{chunk_index})\nContent: {doc.page_content}"
                )
            return "\n\n---\n\n".join(blocks)

        class SearchDocumentsArgs(BaseModel):
            query: str = Field(description="Search query to find relevant document passages")

        return StructuredTool(
            name="search_documents",
            description="Search uploaded documents in this workspace. Pass a focused `query`.",
            args_schema=SearchDocumentsArgs,
            func=search_documents,
        )

    def _resolve_host_url(self, url: str) -> str:
        if not url:
            return url
        is_docker = os.path.exists("/.dockerenv") or os.path.exists("/proc/self/cgroup")
        if is_docker and ("localhost" in url or "127.0.0.1" in url):
            host_replacement = "host.docker.internal"
            return url.replace("localhost", host_replacement).replace("127.0.0.1", host_replacement)
        return url

    def create_api_tool(self, api_tool_config: dict) -> StructuredTool:
        def call_api(**kwargs: Any) -> str:
            try:
                method = api_tool_config.get("method", "GET").upper()
                url = api_tool_config.get("url")
                if not url:
                    return "Error: API URL is not configured"
                url = self._resolve_host_url(url)
                headers = api_tool_config.get("headers", {}) or {}
                base_params = api_tool_config.get("params", {}) or {}
                filtered = {k: v for k, v in kwargs.items() if v is not None and v != ""}
                params = {**base_params, **filtered}
                if method == "GET":
                    response = httpx.get(url, headers=headers, params=params, timeout=10.0)
                elif method == "POST":
                    body = {**filtered}
                    print(body)
                    print(headers)
                    print(url)
                    response = httpx.post(url, headers=headers, json=body, timeout=10.0)
                elif method == "PUT":
                    body = {**filtered}
                    response = httpx.put(url, headers=headers, json=body, timeout=10.0)
                elif method == "DELETE":
                    response = httpx.delete(url, headers=headers, params=params, timeout=10.0)
                else:
                    return f"Unsupported HTTP method: {method}"
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    try:
                        error_body = e.response.json()
                    except Exception:
                        error_body = e.response.text

                    return json.dumps({
                        "error": True,
                        "status_code": e.response.status_code,
                        "details": error_body
                    }, ensure_ascii=False)
                try:
                    return json.dumps(response.json(), ensure_ascii=False)
                except Exception:
                    return json.dumps({"data": response.text}, ensure_ascii=False)

            except httpx.HTTPError as e:
                return f"HTTP error calling API: {e}"

        tool_name = api_tool_config.get("name", "api_tool")
        tool_description = api_tool_config.get("description", "Call external API")
        body_schema = api_tool_config.get("body_schema") or {}
        if isinstance(body_schema, dict) and body_schema:
            keys = ", ".join(body_schema.keys())
            tool_description += f" Required body fields: {keys}."
        

        def generate_model(schema: dict) -> type[BaseModel]:
            fields = {}

            for field_name, meta in schema.items():
                field_type = meta["type"]
                required = meta.get("required", True)
                if field_type == "string":
                    py_type = str
                elif field_type == "int":
                    py_type = int
                elif field_type == "email":
                    py_type = EmailStr
                else:
                    py_type = str  # fallback

                if not required:
                    py_type = Optional[py_type]
                    default = None
                else:
                    default = ...

                fields[field_name] = (py_type, default)

            return create_model("DynamicModel", **fields)

        schema = generate_model(api_tool_config.get("body_schema") or {})
        print(schema)
        return StructuredTool(
            name=tool_name,
            description=tool_description,
            func=call_api,
            args_schema=schema,
        )

    def build_graph_from_config(
        self,
        config: dict,
        system_prompt: str,
        db: DatabaseSession,
        workspace_id: int,
    ) -> StateGraph:
        normalized = self._normalize_graph_config(config, system_prompt)
        gemini_model = self._optional_gemini_model(normalized.get("gemini_model")) or settings.GEMINI_MODEL
        llm = self._get_llm(gemini_model)
        raw_nodes = normalized.get("nodes", [])
        if not raw_nodes:
            raise ValueError("No nodes found in graph config")

        valid_nodes: List[dict] = []
        for node in raw_nodes:
            if isinstance(node, dict) and "id" in node:
                valid_nodes.append(node)
            elif isinstance(node, str):
                try:
                    parsed = json.loads(node)
                    if isinstance(parsed, dict) and "id" in parsed:
                        valid_nodes.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    continue
        if not valid_nodes:
            raise ValueError("No valid nodes found in graph config")

        nodes = {n["id"]: n for n in valid_nodes}
        workflow = StateGraph(dict)
        for node_id, node_config in nodes.items():
            workflow.add_node(
                node_id,
                self._make_node_executor(node_config, workspace_id, db, llm=llm),
            )
        workflow.set_entry_point(normalized["entry_node_id"])

        for node_id, node_config in nodes.items():
            transitions = node_config.get("transitions", [])
            valid_targets = {
                t["target_node_id"] for t in transitions if t.get("target_node_id") in nodes
            }
            if not valid_targets:
                workflow.add_edge(node_id, END)
                continue
            mapping = {t: t for t in valid_targets}
            mapping["end"] = END
            workflow.add_conditional_edges(
                node_id,
                self._make_transition_selector(node_config, nodes, llm=llm),
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
    ) -> tuple[str, Dict[str, Any]]:
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
        final_messages = result["messages"]
        usage = _aggregate_usage_from_messages(final_messages)
        for msg in reversed(final_messages):
            if not isinstance(msg, AIMessage):
                continue
            if _tool_calls_from_ai_message(msg):
                continue
            text = _text_from_message_content(msg.content)
            if text:
                return text, usage
        raise RuntimeError("Graph returned no final assistant message with text content")

    def _normalize_graph_config(self, config: dict, default_prompt: str) -> dict:
        gemini_model = self._optional_gemini_model(config.get("gemini_model"))
        if config.get("nodes") and config.get("entry_node_id"):
            nodes = config.get("nodes")
            if isinstance(nodes, str):
                try:
                    nodes = json.loads(nodes)
                except (json.JSONDecodeError, TypeError):
                    try:
                        import ast

                        nodes = ast.literal_eval(nodes)
                    except (ValueError, SyntaxError):
                        nodes = []
            entry_node_id = config.get("entry_node_id")
            if isinstance(entry_node_id, str):
                entry_node_id = entry_node_id.strip().strip('"').strip("'")
            return {
                "entry_node_id": entry_node_id,
                "nodes": nodes if isinstance(nodes, list) else [],
                "gemini_model": gemini_model,
            }
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
            "gemini_model": gemini_model,
        }

    def _make_node_executor(
        self,
        node_config: dict,
        workspace_id: int,
        db: DatabaseSession,
        *,
        llm: ChatGoogleGenerativeAI,
    ):
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
            api_tools_db = api_tool_repo.get_api_tools_by_ids(
                db,
                workspace_id=workspace_id,
                tool_ids=api_tool_ids,
            )
            for api_tool_db in api_tools_db:
                cfg = {
                    "name": api_tool_db["name"],
                    "description": api_tool_db.get("description"),
                    "url": api_tool_db["url"],
                    "method": api_tool_db["method"],
                    "headers": api_tool_db.get("headers") or {},
                    "params": api_tool_db.get("params") or {},
                    "body_schema": api_tool_db.get("body_schema") or {},
                }
                tools.append(self.create_api_tool(cfg))

        tool_by_name = {t.name: t for t in tools}
        node_prompt = self._compose_system_prompt(
            node_config.get("system_prompt") or "",
            has_tools=bool(tools),
        )
        llm_bound = llm.bind_tools(tools, tool_choice="required") if tools else llm

        def node_runner(state: dict) -> dict:
            messages: List[Any] = list(state.get("messages", []))

            llm_messages = [SystemMessage(content=node_prompt)] + messages

            try:
                response = llm_bound.invoke(llm_messages)
            except Exception as e:
                logger.exception("LLM invoke failed: %s", e)
                messages.append(
                    AIMessage(content="Извините, произошла ошибка при обработке запроса.")
                )
                return {"messages": messages, "_last_node_id": node_config["id"]}

            if not isinstance(response, AIMessage):
                response = AIMessage(content=_text_from_message_content(response))

            messages.append(response)

            calls = _tool_calls_from_ai_message(response)

            if not calls or not tools:
                return {"messages": messages, "_last_node_id": node_config["id"]}

            tc = calls[0]

            name = tc["name"]
            args = tc["args"]
            tid = tc["id"]

            tool = tool_by_name.get(name)

            try:
                if tool:
                    out = tool.invoke(args)
                else:
                    out = f"Unknown tool: {name}"
            except Exception as e:
                out = f"Error running tool {name}: {e}"

            messages.append(ToolMessage(content=str(out), tool_call_id=tid))
            final_response = llm.invoke(
                [SystemMessage(content=node_prompt)] + messages
            )

            if not isinstance(final_response, AIMessage):
                final_response = AIMessage(content=_text_from_message_content(final_response))

            messages.append(final_response)

            return {"messages": messages, "_last_node_id": node_config["id"]}

        return node_runner

    def _make_transition_selector(
        self,
        node_config: dict,
        nodes: Dict[str, dict],
        *,
        llm: ChatGoogleGenerativeAI,
    ):
        def selector(state: dict) -> str:
            msgs = state.get("messages", [])
            last_user = self._get_last_user_message(msgs)
            last_ai = self._get_last_ai_message(msgs)
            # Сначала always/keyword (порядок в списке). llm_routing в _transition_matches не матчится.
            for transition in node_config.get("transitions", []):
                tid = transition["target_node_id"]
                if tid not in nodes:
                    continue
                if self._transition_matches(
                    transition.get("condition") or {},
                    last_user,
                    last_ai,
                ):
                    return tid
            llm_routing = [
                t
                for t in node_config.get("transitions", [])
                if (t.get("condition") or {}).get("type") == "llm_routing"
            ]
            if llm_routing:
                picked = self._llm_select_next_node(
                    msgs,
                    llm_routing,
                    nodes,
                    node_config.get("system_prompt", ""),
                    llm=llm,
                )
                if picked:
                    return picked
            return "end"

        return selector

    def _transition_matches(
        self,
        condition: dict,
        last_user_message: Optional[HumanMessage],
        last_ai_message: Optional[AIMessage],
    ) -> bool:
        ctype = (condition or {}).get("type", "always")
        if ctype == "always":
            return True
        if ctype == "keyword":
            keyword = (condition or {}).get("value", "")
            if not keyword:
                return False
            k = keyword.lower()
            if last_user_message and k in (last_user_message.content or "").lower():
                return True
            if last_ai_message and k in (last_ai_message.content or "").lower():
                return True
            return False
        if ctype == "llm_routing":
            return False
        return False

    def _llm_select_next_node(
        self,
        messages: List[Any],
        transitions: List[dict],
        nodes: Dict[str, dict],
        routing_prompt: str = "",
        *,
        llm: ChatGoogleGenerativeAI,
    ) -> Optional[str]:
        if not transitions:
            return None
        available = []
        for tr in transitions:
            tid = tr["target_node_id"]
            if tid in nodes:
                n = nodes[tid]
                available.append({"id": tid, "name": n.get("name", tid), "description": n.get("system_prompt", "")})
        if not available:
            return None
        lines = [f"- {a['id']}: {a['name']}" + (f" — {a['description']}" if a["description"] else "") for a in available]
        nodes_block = "\n".join(lines)
        instr = (routing_prompt or "").strip()
        if "{nodes}" in instr:
            instr = instr.replace("{nodes}", nodes_block)
        elif instr:
            instr = f"{instr}\n\nДоступные узлы:\n{nodes_block}"
        else:
            instr = f"Выбери ровно один id узла из списка (только id, без текста):\n{nodes_block}"

        last_user = self._get_last_user_message(messages)
        if not last_user:
            return available[0]["id"]
        try:
            out = llm.invoke(
                [
                    SystemMessage(content=instr),
                    HumanMessage(content=f"Запрос пользователя: {last_user.content}"),
                ]
            )
            text = _text_from_message_content(out.content).strip().lower()
            for a in available:
                if a["id"].lower() == text:
                    return a["id"]
            for a in available:
                if a["id"].lower() in text:
                    return a["id"]
            return available[0]["id"]
        except Exception:
            return available[0]["id"]

    def _get_last_ai_message(self, messages: List[Any]) -> Optional[AIMessage]:
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return message
        return None

    def _get_last_user_message(self, messages: List[Any]) -> Optional[HumanMessage]:
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                if message.additional_kwargs.get("from_tool"):
                    continue
                return message
        return None


langchain_service = LangChainService()
