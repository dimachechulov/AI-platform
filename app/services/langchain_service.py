from typing import List, Dict, Optional, Any
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import Tool, StructuredTool
try:
    from pydantic.v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field
from typing import Type
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from app.core.config import settings
from app.db.database import DatabaseSession
from app.db import repositories as repo
from app.services.vector_store import vector_store
from app.core.tracing import get_callback_manager
import httpx
import json

logger = logging.getLogger(__name__)

# Схема для API инструментов - используем pydantic.v1 для совместимости с langchain
class ApiToolArgsSchema(BaseModel):
    """Schema for API tool arguments - accepts any additional parameters"""
    class Config:
        extra = "allow"


class LangChainService:
    """Сервис для работы с LangChain и Gemini"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.7,
            #api_version="v1",
            convert_system_message_to_human=True,
            callback_manager=get_callback_manager(),
        )

    def _build_tool_instruction(self, tools: List[Tool]) -> str:
        """Generate instruction text describing available tools."""
        if not tools:
            return ""

        lines = [
                "AVAILABLE TOOLS:",
                "You have access to the following tools. You MUST always use a tool for any actionable user request.",
                "",
                "YOU **MUST** ALWAYS USE TOOLS. NO EXCEPTIONS.",
                "- Always extract ALL parameters from the user's message (dates, queries, IDs, emails, phones, names, etc.).",
                "- If a required parameter is missing, still call the tool and pass an empty string \"\".",
                "",
                "HOW TO CALL A TOOL:",
                "Your ENTIRE response must be ONLY a valid JSON object in this exact format:",
                "{\"action\":\"tool\",\"tool_name\":\"<tool_name>\",\"arguments\":{\"param1\":\"value1\",\"param2\":\"value2\"}}",
                "",
                "CRITICAL FORMATTING RULES:",
                "- Your response must be ONLY the JSON object — nothing else!",
                "- DO NOT write any text, explanations, or code before or after the JSON.",
                "- DO NOT use markdown code blocks (```json or ```).",
                "- DO NOT write Python code or function definitions like: tool_name(param1='value1').",
                "- DO NOT write function calls in Python syntax — ONLY use JSON format.",
                "- JSON must be valid: start with { and end with }.",
                "- All parameter values must be quoted strings.",
                "- Example of CORRECT format: {\"action\":\"tool\",\"tool_name\":\"book_appointment\",\"arguments\":{\"service_type\":\"consultation\"}}",
                "- Example of WRONG format: book_appointment(service_type='consultation') — this will NOT work!",
                "",
                "AVAILABLE TOOLS:",
            ]

        for tool in tools:
            tool_desc = tool.description or 'No description'
            lines.append(f"- {tool.name}: {tool_desc}")
        lines.append("")
        lines.append("EXAMPLES:")
        # Генерируем примеры динамически на основе доступных инструментов
        example_count = 0
        for tool in tools[:2]:  # Показываем максимум 2 примера
            if example_count >= 2:
                break
            # Определяем примерные параметры на основе схемы инструмента
            tool_args = {}
            if hasattr(tool, 'args_schema') and tool.args_schema:
                # Пытаемся получить поля из схемы
                try:
                    schema_fields = tool.args_schema.__fields__ if hasattr(tool.args_schema, '__fields__') else {}
                    for field_name, field_info in list(schema_fields.items())[:2]:  # Берем первые 2 поля
                        if 'date' in field_name.lower():
                            tool_args[field_name] = "2024-01-20"
                        elif 'query' in field_name.lower() or 'search' in field_name.lower():
                            tool_args[field_name] = "example query"
                        else:
                            tool_args[field_name] = "example_value"
                except Exception:
                    # Если не удалось получить схему, используем примерные значения
                    pass
            
            if not tool_args:
                # Если не удалось определить параметры, используем пустой объект
                tool_args = {}
            
            # lines.append(f'Example {example_count + 1}: To call {tool.name} with {tool_args}, respond with:')
            # lines.append(f'{{"action":"tool","tool_name":"{tool.name}","arguments":{json.dumps(tool_args)}}}')
            # lines.append("")
            example_count += 1
        lines.append("")
        # lines.append("IMPORTANT REMINDERS:")
        # lines.append("- Extract all parameters from the user's message (dates, queries, IDs, etc.)")
        # lines.append("- If a tool requires parameters that are missing, you MUST ask the user for them in natural language - DO NOT call the tool with empty values, placeholders, or default values")
        # lines.append("- Only call a tool when you have ALL required parameters with real values from the user")
        # lines.append("- If no tool is needed, respond in natural language with the final answer")
        # lines.append("- When calling a tool, respond with ONLY the JSON object - no other text!")
        # lines.append("- NEVER use placeholder values like 'имя', 'телефон', 'email' - always ask the user for real information first")
        return "\n".join(lines)

    def _compose_system_prompt(self, base_prompt: str, tool_instruction: str) -> str:
        base = base_prompt.strip() if base_prompt else ""
        if tool_instruction:
            if base:
                return f"{base}\n\n{tool_instruction}"
            return tool_instruction
        return base or "You are a helpful assistant."

    def _normalize_content(self, content: Any) -> str:
        """Нормализует контент ответа LLM в строку."""
        if content is None:
            return ""
        if isinstance(content, str):
            normalized = content.strip()
            # Убираем странные ключи или переменные, которые могут появиться
            if normalized.startswith("_") and ("_prompt" in normalized or "_request" in normalized):
                return ""
            return normalized
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    # Извлекаем текст из словаря
                    text = item.get("text") or item.get("content") or ""
                    if text:
                        parts.append(str(text))
                else:
                    parts.append(str(item))
            result = " ".join(parts).strip()
            # Проверяем на странные ключи
            if result.startswith("_") and ("_prompt" in result or "_request" in result):
                return ""
            return result
        # Для других типов просто преобразуем в строку
        result = str(content).strip()
        if result.startswith("_") and ("_prompt" in result or "_request" in result):
            return ""
        return result

    def _extract_tool_calls(self, content: Any, messages_context: Optional[List[Any]] = None, available_tools: Optional[List[Tool]] = None) -> List[Dict[str, Any]]:
        """Parse tool calls from model response content."""
        normalized = self._normalize_content(content)
        if not normalized:
            return []
        
        import re
        payloads = []
        
        # Сначала пытаемся распарсить весь контент как JSON
        try:
            payload = json.loads(normalized)
            payloads = payload if isinstance(payload, list) else [payload]
        except json.JSONDecodeError:
            # Если не получилось, пытаемся найти JSON в тексте
            json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*"action"\s*:\s*"tool"(?:[^{}]|(?:\{[^{}]*\}))*\}'
            matches = re.findall(json_pattern, normalized, re.DOTALL)
            if not matches:
                # Пробуем более простой паттерн
                json_pattern = r'\{[^{}]*"action"[^{}]*"tool"[^{}]*\}'
                matches = re.findall(json_pattern, normalized, re.DOTALL)
            
            # Пытаемся распарсить найденные JSON
            for match in matches:
                try:
                    cleaned = match.strip()
                    if cleaned.startswith('```'):
                        lines = cleaned.split('\n')
                        cleaned = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned
                    elif '```json' in cleaned or '```' in cleaned:
                        start = cleaned.find('{')
                        end = cleaned.rfind('}')
                        if start >= 0 and end > start:
                            cleaned = cleaned[start:end+1]
                    payload = json.loads(cleaned)
                    payloads.append(payload)
                except json.JSONDecodeError:
                    continue
            
            # Если JSON не найден, пробуем распознать простые форматы
            if not payloads:
                python_call_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)'
                python_match = re.search(python_call_pattern, normalized, re.DOTALL)
                if python_match:
                    tool_name = python_match.group(1)
                    params_str = python_match.group(2)
                    
                    # Парсим параметры в формате key='value' или key=value
                    args = {}
                    # Паттерн для параметров: key='value' или key=value или key=123
                    param_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*['\"]?([^,'\"]+)['\"]?"
                    param_matches = re.findall(param_pattern, params_str)
                    for param_name, param_value in param_matches:
                        # Убираем кавычки если есть
                        param_value = param_value.strip().strip("'\"")
                        # Пытаемся определить тип значения
                        if param_value.isdigit():
                            args[param_name] = int(param_value)
                        elif param_value.replace('.', '', 1).isdigit():
                            args[param_name] = float(param_value)
                        else:
                            args[param_name] = param_value
                    
                    if tool_name and args:
                        payloads.append({
                            "action": "tool",
                            "tool_name": tool_name,
                            "arguments": args
                        })
                
                # Проверяем формат кортежа параметров без имени функции
                # Пример: (service_type='consultation', slot_id=1, customer_name='Дмитрий')
                if not payloads:
                    tuple_pattern = r'^\s*\(([^)]+)\)\s*$'
                    tuple_match = re.match(tuple_pattern, normalized.strip())
                    if tuple_match:
                        params_str = tuple_match.group(1)
                        
                        # Парсим параметры в формате key='value' или key=value
                        args = {}
                        param_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*['\"]?([^,'\"]+)['\"]?"
                        param_matches = re.findall(param_pattern, params_str)
                        for param_name, param_value in param_matches:
                            # Убираем кавычки если есть
                            param_value = param_value.strip().strip("'\"")
                            # Пытаемся определить тип значения
                            if param_value.isdigit():
                                args[param_name] = int(param_value)
                            elif param_value.replace('.', '', 1).isdigit():
                                args[param_name] = float(param_value)
                            else:
                                args[param_name] = param_value
                        
                        # Если нашли параметры, определяем инструмент на основе доступных инструментов
                        if args and available_tools:
                            # Определяем наиболее подходящий инструмент на основе параметров
                            best_tool = None
                            best_match_score = 0
                            
                            for tool in available_tools:
                                # Получаем схему инструмента
                                tool_schema_fields = set()
                                if hasattr(tool, 'args_schema') and tool.args_schema:
                                    try:
                                        schema_fields = tool.args_schema.__fields__ if hasattr(tool.args_schema, '__fields__') else {}
                                        tool_schema_fields = set(schema_fields.keys())
                                    except Exception:
                                        pass
                                
                                # Также проверяем описание инструмента для определения требуемых параметров
                                tool_description = (tool.description or "").lower()
                                
                                # Подсчитываем совпадения параметров
                                match_score = 0
                                param_names = set(args.keys())
                                
                                # Проверяем совпадение с полями схемы
                                if tool_schema_fields:
                                    common_params = param_names & tool_schema_fields
                                    match_score += len(common_params) * 2  # Вес для совпадений со схемой
                                
                                # Проверяем упоминание параметров в описании
                                for param_name in param_names:
                                    if param_name.lower() in tool_description:
                                        match_score += 1
                                
                                # Специальная логика для определения типа инструмента
                                # Если есть customer_name, customer_phone, customer_email, slot_id - это book_appointment
                                has_customer_data = 'customer_name' in param_names or 'customer_phone' in param_names or 'customer_email' in param_names
                                has_slot_id = 'slot_id' in param_names
                                
                                if has_customer_data or has_slot_id:
                                    # Это явно вызов для создания записи
                                    if 'book' in tool.name.lower() or 'appointment' in tool.name.lower() or 'create' in tool.name.lower():
                                        match_score += 20  # Высокий приоритет для book_appointment
                                    elif 'available' in tool.name.lower() or 'slot' in tool.name.lower() or 'get' in tool.name.lower():
                                        match_score -= 5  # Понижаем приоритет для get_available_slots
                                
                                # Если есть date и service_type, но нет customer данных - это get_available_slots
                                if 'date' in param_names and 'service_type' in param_names:
                                    if not has_customer_data and not has_slot_id:
                                        if 'available' in tool.name.lower() or 'slot' in tool.name.lower() or 'get' in tool.name.lower():
                                            match_score += 15  # Высокий приоритет для get_available_slots
                                        elif 'book' in tool.name.lower() or 'appointment' in tool.name.lower():
                                            match_score -= 5  # Понижаем приоритет для book_appointment
                                
                                if match_score > best_match_score:
                                    best_match_score = match_score
                                    best_tool = tool
                            
                            # Если нашли подходящий инструмент, создаем вызов
                            if best_tool and best_match_score > 0:
                                logger.info(f"Determined tool '{best_tool.name}' from tuple parameters with score {best_match_score}")
                                payloads.append({
                                    "action": "tool",
                                    "tool_name": best_tool.name,
                                    "arguments": args
                                })
                            # Если не нашли точного совпадения, но есть только один инструмент, используем его
                            elif len(available_tools) == 1:
                                logger.info(f"Using single available tool '{available_tools[0].name}' for tuple parameters")
                                payloads.append({
                                    "action": "tool",
                                    "tool_name": available_tools[0].name,
                                    "arguments": args
                                })
                            else:
                                logger.warning(f"Could not determine tool from tuple parameters. Available tools: {[t.name for t in available_tools]}, Parameters: {list(args.keys())}")
                
                # Если не нашли Python-вызов, проверяем формат с переносом строки:
                # tool_name
                # (param1=value1, param2=value2)
                if not payloads:
                    lines = normalized.strip().split('\n')
                    if len(lines) >= 2:
                        first_line = lines[0].strip()
                        second_line = lines[1].strip()
                        # Проверяем, что первая строка - имя инструмента, вторая - параметры в скобках
                        if (re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', first_line) and 
                            second_line.startswith('(') and second_line.endswith(')')):
                            tool_name = first_line
                            params_str = second_line[1:-1]  # Убираем скобки
                            
                            args = {}
                            param_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*['\"]?([^,'\"]+)['\"]?"
                            param_matches = re.findall(param_pattern, params_str)
                            for param_name, param_value in param_matches:
                                param_value = param_value.strip().strip("'\"")
                                if param_value.isdigit():
                                    args[param_name] = int(param_value)
                                elif param_value.replace('.', '', 1).isdigit():
                                    args[param_name] = float(param_value)
                                else:
                                    args[param_name] = param_value
                            
                            if tool_name and args:
                                payloads.append({
                                    "action": "tool",
                                    "tool_name": tool_name,
                                    "arguments": args
                                })
                
                # Сначала проверяем, не является ли ответ результатом инструмента
                # Паттерн: "tool_name:" в начале строки, за которым следует JSON массив или объект
                result_match = None
                if not payloads:
                    result_pattern = r'^([a-zA-Z_][a-zA-Z0-9_]*?):\s*(\[|\{)'
                    result_match = re.match(result_pattern, normalized.strip())
                if result_match:
                    # Это результат инструмента - модель вернула результат вместо вызова инструмента
                    # Пытаемся определить правильный инструмент на основе доступных инструментов
                    tool_indicator = result_match.group(1).lower()
                    
                    if available_tools:
                        # Ищем инструмент, чье имя похоже на индикатор
                        # Используем частичное совпадение для гибкости
                        for tool in available_tools:
                            tool_name_lower = tool.name.lower()
                            # Проверяем, есть ли совпадение в названии инструмента или индикаторе
                            if (tool_indicator in tool_name_lower or 
                                any(word in tool_indicator for word in tool_name_lower.split('_') if len(word) > 3) or
                                any(word in tool_name_lower for word in tool_indicator.split('_') if len(word) > 3)):
                                
                                # Нашли подходящий инструмент, извлекаем параметры из истории
                                args = {}
                                if messages_context:
                                    # Ищем параметры в истории сообщений пользователя
                                    search_text = normalized
                                    for msg in reversed(messages_context):
                                        if isinstance(msg, HumanMessage) and not msg.additional_kwargs.get("from_tool"):
                                            msg_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                                            search_text += " " + msg_content
                                            break
                                    
                                    # Пытаемся извлечь параметры на основе схемы инструмента
                                    if hasattr(tool, 'args_schema') and tool.args_schema:
                                        try:
                                            # Получаем поля схемы
                                            schema_fields = tool.args_schema.__fields__ if hasattr(tool.args_schema, '__fields__') else {}
                                            
                                            # Ищем дату в тексте (наиболее распространенный параметр)
                                            date_patterns = [
                                                r'\b(\d{4}-\d{2}-\d{2})\b',  # YYYY-MM-DD
                                                r'\b(\d{2})\.(\d{2})\.(\d{4})\b',  # DD.MM.YYYY
                                            ]
                                            for pattern in date_patterns:
                                                date_match = re.search(pattern, search_text)
                                                if date_match:
                                                    if len(date_match.groups()) == 1:
                                                        date_value = date_match.group(1)
                                                    else:
                                                        day, month, year = date_match.groups()
                                                        date_value = f"{year}-{month}-{day}"
                                                    
                                                    # Проверяем, есть ли поле date в схеме
                                                    for field_name in schema_fields.keys():
                                                        if 'date' in field_name.lower():
                                                            args[field_name] = date_value
                                                            break
                                                    if args:
                                                        break
                                        except Exception:
                                            pass
                                
                                # Создаем вызов инструмента
                                payloads.append({
                                    "action": "tool",
                                    "tool_name": tool.name,
                                    "arguments": args
                                })
                                break  # Используем первый подходящий инструмент
                
                # Паттерн для формата "tool_name_for_param:value" или "tool_name:value"
                # Пример: available_slots_for_date:2025-12-08 или get_available_slots:2025-12-08
                if not payloads:
                    simple_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*?)(?:_for_([a-zA-Z_][a-zA-Z0-9_]*))?:\s*([^\s,\.\[\{]+)'
                    simple_matches = re.findall(simple_pattern, normalized)
                    
                    for match in simple_matches:
                        tool_base, param_name, value = match
                        
                        # Определяем имя инструмента и параметр без хардкода
                        # Используем tool_base как имя инструмента напрямую, если оно выглядит полным
                        if param_name:
                            # Формат: tool_name_for_param:value
                            tool_name = tool_base
                            args = {param_name: value}
                        else:
                            # Формат: tool_name:value
                            tool_name = tool_base
                            # Пытаемся определить тип параметра по значению
                            # Проверяем, является ли value датой
                            date_match = re.search(r'\b(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\b', value)
                            if date_match:
                                date_str = date_match.group(1)
                                # Конвертируем DD.MM.YYYY в YYYY-MM-DD
                                if '.' in date_str:
                                    parts = date_str.split('.')
                                    if len(parts) == 3:
                                        day, month, year = parts
                                        date_str = f"{year}-{month}-{day}"
                                args = {"date": date_str}
                            else:
                                # По умолчанию используем "query" или "value"
                                args = {"query": value}
                        
                        payloads.append({
                            "action": "tool",
                            "tool_name": tool_name,
                            "arguments": args
                        })
                
                # Если все еще ничего не найдено, ищем имя инструмента и параметры отдельно
                # Это делается без хардкода - инструменты определяются динамически из контекста
                if not payloads and messages_context:
                    # Пытаемся найти упоминание инструментов в контексте
                    # Используем общие паттерны для определения намерения вызова инструмента
                    tool_indicators = []
                    # Ищем слова, которые могут указывать на инструменты (tool-like words)
                    import re
                    tool_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b'
                    potential_tools = re.findall(tool_pattern, normalized)
                    
                    # Пробуем найти дату для определения возможного инструмента
                    date_patterns = [
                        r'\b(\d{4}-\d{2}-\d{2})\b',
                        r'\b(\d{2})\.(\d{2})\.(\d{4})\b',
                    ]
                    # Ищем дату в контенте или истории сообщений
                    search_text = normalized
                    if messages_context:
                        for msg in reversed(messages_context):
                            if isinstance(msg, HumanMessage) and not msg.additional_kwargs.get("from_tool"):
                                search_text += " " + (msg.content if isinstance(msg.content, str) else str(msg.content))
                                break
                    
                    args = {}
                    for pattern in date_patterns:
                        date_match = re.search(pattern, search_text)
                        if date_match:
                            if len(date_match.groups()) == 1:
                                args["date"] = date_match.group(1)
                            else:
                                day, month, year = date_match.groups()
                                args["date"] = f"{year}-{month}-{day}"
                            break
                    
                    # Если найдена дата, пытаемся определить инструмент по контексту
                    # Полагаемся на промпт для определения когда и какие инструменты вызывать
                    # Эта часть остается пустой, так как конкретный инструмент определяется через конфиг
                
                # Если нашли инструмент, но аргументы пустые, пытаемся извлечь параметры из истории
                # Используем общие паттерны (даты, числа, строки) без хардкода конкретных инструментов
                if payloads:
                    for payload in payloads:
                        args = payload.get("arguments") or {}
                        # Если аргументы пустые или неполные, пытаемся извлечь из истории
                        if not args or len(args) == 0:
                                # Ищем дату в истории сообщений
                                if messages_context:
                                    for msg in reversed(messages_context):
                                        if isinstance(msg, HumanMessage) and not msg.additional_kwargs.get("from_tool"):
                                            msg_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                                            date_patterns = [
                                                r'\b(\d{4}-\d{2}-\d{2})\b',
                                                r'\b(\d{2})\.(\d{2})\.(\d{4})\b',
                                            ]
                                            for pattern in date_patterns:
                                                date_match = re.search(pattern, msg_content)
                                                if date_match:
                                                    if len(date_match.groups()) == 1:
                                                        date_value = date_match.group(1)
                                                    else:
                                                        day, month, year = date_match.groups()
                                                        date_value = f"{year}-{month}-{day}"
                                                    
                                                    if not payload.get("arguments"):
                                                        payload["arguments"] = {}
                                                    # Динамически определяем имя параметра
                                                    # Используем "date" как наиболее вероятное, если не определено
                                                    param_name = "date"
                                                    payload["arguments"][param_name] = date_value
                                                    break
                                            if payload.get("arguments"):
                                                break

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
            # Log the query to debug
            logger.info(f"RAG search called with query: '{query}' (type: {type(query)})")
            
            # Ensure query is a string
            if not isinstance(query, str):
                query = str(query) if query else ""
            
            if not query or not query.strip():
                logger.warning("Empty query passed to search_documents")
                return "Please provide a search query."
            
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
        
        # Use StructuredTool with explicit schema to ensure query parameter is passed correctly
        class SearchDocumentsArgs(BaseModel):
            query: str = Field(description="The search query to find relevant documents")
        
        return StructuredTool(
            name="search_documents",
            description="Search for information in uploaded documents. Always provide a 'query' parameter with the search text.",
            args_schema=SearchDocumentsArgs,
            func=search_documents
        )
    
    def _resolve_host_url(self, url: str) -> str:
        """Заменяет localhost на правильный адрес для доступа к хосту из Docker контейнера"""
        import os
        
        if not url:
            return url
        
        # Проверяем, запущены ли мы в Docker
        is_docker = os.path.exists("/.dockerenv") or os.path.exists("/proc/self/cgroup")
        
        if is_docker and ("localhost" in url or "127.0.0.1" in url):
            # Используем host.docker.internal для доступа к хосту из контейнера
            # Это должно быть настроено в docker-compose.yml через extra_hosts
            host_replacement = "host.docker.internal"
            new_url = url.replace("localhost", host_replacement).replace("127.0.0.1", host_replacement)
            return new_url
        
        return url
    
    def create_api_tool(self, api_tool_config: dict) -> Tool:
        """Создание инструмента для вызова внешнего API"""
        def call_api(**kwargs) -> str:
            """Вызов внешнего API"""
            try:
                method = api_tool_config.get("method", "GET").upper()
                url = api_tool_config.get("url")
                
                if not url:
                    return "Error: API URL is not configured"
                
                # Разрешаем адрес хоста для Docker окружения
                url = self._resolve_host_url(url)
                
                headers = api_tool_config.get("headers", {}) or {}
                base_params = api_tool_config.get("params", {}) or {}
                body_schema = api_tool_config.get("body_schema", {}) or {}
                
                # Фильтруем пустые значения из kwargs
                filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None and v != ""}
                
                # Объединяем базовые параметры с параметрами из вызова
                params = {**base_params, **filtered_kwargs}
                
                if method == "GET":
                    response = httpx.get(url, headers=headers, params=params, timeout=10.0)
                elif method == "POST":
                    # Объединяем body_schema с параметрами из вызова
                    body = {**body_schema, **filtered_kwargs}
                    response = httpx.post(url, headers=headers, json=body, timeout=10.0)
                elif method == "PUT":
                    body = {**body_schema, **filtered_kwargs}
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
            except httpx.ConnectError as e:
                error_msg = str(e)
                if "Connection refused" in error_msg:
                    return f"Connection Error: Unable to connect to {url}. The server may be down or the URL is incorrect. Error: {error_msg}"
                else:
                    return f"Connection Error: Failed to connect to {url}. Error: {error_msg}"
            except httpx.TimeoutException as e:
                return f"Timeout Error: Request to {url} timed out after 10 seconds. The server may be slow or unavailable."
            except httpx.HTTPStatusError as e:
                try:
                    error_body = e.response.text
                except:
                    error_body = "No error details available"
                return f"HTTP Error {e.response.status_code}: {error_body}"
            except httpx.RequestError as e:
                return f"Request Error: Failed to send request to {url}. Error: {str(e)}"
            except Exception as e:
                return f"Unexpected error calling API: {str(e)}"
        
        # Создаем Tool с подробным описанием для лучшего понимания LLM
        tool_name = api_tool_config.get("name", "api_tool")
        tool_description = api_tool_config.get("description", "Call external API")
        
        # Добавляем информацию о требуемых параметрах из body_schema
        body_schema = api_tool_config.get("body_schema") or {}
        if body_schema and isinstance(body_schema, dict) and body_schema:
            # Все параметры в body_schema считаются обязательными
            required_params = list(body_schema.keys())
            if required_params:
                params_list = ", ".join(required_params)
                tool_description += f" REQUIRED PARAMETERS: {params_list}. You MUST collect all these parameters from the user before calling this tool. If any parameter is missing, ask the user for it in natural language - DO NOT use placeholder values, empty strings, or default values."
        
        # Используем схему, созданную на уровне модуля
        # Она использует pydantic.v1 для совместимости с langchain
        args_schema = ApiToolArgsSchema
        
        # Используем StructuredTool для поддержки множественных параметров
        return StructuredTool(
            name=tool_name,
            description=tool_description,
            func=call_api,
            args_schema=args_schema
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
        
        # Process nodes - handle both dicts and JSON strings
        raw_nodes = normalized.get("nodes", [])
        if not raw_nodes:
            logger.error(f"No nodes in normalized config. Config: {config}, Normalized: {normalized}")
            raise ValueError("No nodes found in graph config")
        
        valid_nodes = []
        for i, node in enumerate(raw_nodes):
            if isinstance(node, dict):
                if "id" in node:
                    valid_nodes.append(node)
                else:
                    logger.warning(f"Node at index {i} is a dict but missing 'id' field: {node}")
            elif isinstance(node, str):
                # Try to parse JSON string
                try:
                    parsed = json.loads(node)
                    if isinstance(parsed, dict) and "id" in parsed:
                        valid_nodes.append(parsed)
                    else:
                        logger.warning(f"Parsed node at index {i} is not a valid dict with 'id': {parsed}")
                except (json.JSONDecodeError, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to parse node at index {i} as JSON: {node[:100]}, error: {e}")
            else:
                logger.warning(f"Node at index {i} is unexpected type {type(node)}: {node}")
        
        if not valid_nodes:
            logger.error(f"No valid nodes found. Raw nodes count: {len(raw_nodes)}, First node type: {type(raw_nodes[0]) if raw_nodes else None}, Config keys: {list(config.keys()) if isinstance(config, dict) else None}")
            raise ValueError("No valid nodes found in graph config")
        
        nodes = {node["id"]: node for node in valid_nodes}

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
        
        # Ищем последний ответ AI (игнорируя сообщения от инструментов)
        # Проходим по сообщениям в обратном порядке, чтобы найти последний настоящий ответ AI
        last_ai_message = None
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage):
                content = self._normalize_content(msg.content)
                # Проверяем, что это не JSON вызов инструмента
                if content and not content.strip().startswith('{') and not content.strip().startswith('['):
                    # Проверяем, что это не вызов инструмента
                    tool_calls = self._extract_tool_calls(content)
                    if not tool_calls:
                        last_ai_message = content
                        break
        
        if last_ai_message:
            return last_ai_message
        
        # Если не нашли ответ, пытаемся найти любой AI ответ
        last_ai = self._get_last_ai_message(final_messages)
        if last_ai and last_ai.content:
            normalized = self._normalize_content(last_ai.content)
            # Проверяем, что это не вызов инструмента
            tool_calls = self._extract_tool_calls(normalized)
            if normalized and not tool_calls:
                return normalized
        
        # Если все еще нет ответа, возвращаем сообщение об ошибке
        # НЕ возвращаем вопрос пользователя - это плохой UX
        return "Извините, не удалось обработать запрос. Попробуйте переформулировать вопрос."

    def _normalize_graph_config(self, config: dict, default_prompt: str) -> dict:
        if config.get("nodes") and config.get("entry_node_id"):
            # Parse nodes if it's a string (can be JSON or Python repr)
            nodes = config.get("nodes")
            if isinstance(nodes, str):
                try:
                    # Try JSON first
                    nodes = json.loads(nodes)
                except (json.JSONDecodeError, TypeError):
                    try:
                        # Try Python literal_eval (handles single quotes)
                        import ast
                        nodes = ast.literal_eval(nodes)
                    except (ValueError, SyntaxError) as e:
                        logger.warning(f"Failed to parse nodes string: {e}")
                        nodes = []
            
            # Parse entry_node_id if it's a JSON string (remove quotes)
            entry_node_id = config.get("entry_node_id")
            if isinstance(entry_node_id, str):
                if entry_node_id.startswith('"') and entry_node_id.endswith('"'):
                    try:
                        entry_node_id = json.loads(entry_node_id)
                    except (json.JSONDecodeError, TypeError):
                        entry_node_id = entry_node_id.strip('"\'')
                elif entry_node_id.startswith("'") and entry_node_id.endswith("'"):
                    entry_node_id = entry_node_id.strip("'\"")
            
            return {
                "entry_node_id": entry_node_id,
                "nodes": nodes if isinstance(nodes, list) else []
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

            max_iterations = 10  # Защита от бесконечного цикла
            iteration = 0
            
            # Если есть инструменты, используем bind_tools для их привязки к LLM
            llm_with_tools = self.llm
            if tools:
                try:
                    # Пытаемся использовать встроенный механизм вызова инструментов
                    llm_with_tools = self.llm.bind_tools(tools)
                except Exception:
                    # Если не поддерживается, используем старый подход с JSON
                    llm_with_tools = self.llm
            
            while iteration < max_iterations:
                iteration += 1
                llm_messages = [SystemMessage(content=node_prompt)] + messages
                
                # Вызываем LLM с обработкой ошибок
                try:
                    response = llm_with_tools.invoke(llm_messages)
                except IndexError as e:
                    # Обработка случая, когда Gemini API возвращает пустой ответ
                    logger.warning(f"Empty response from LLM (IndexError): {e}")
                    messages.append(
                        AIMessage(content="Извините, произошла ошибка при обработке запроса. Попробуйте переформулировать вопрос.")
                    )
                    break
                except Exception as e:
                    # Обработка других ошибок LLM
                    logger.error(f"Error calling LLM: {e}")
                    messages.append(
                        AIMessage(content="Извините, произошла ошибка при обработке запроса. Попробуйте переформулировать вопрос.")
                    )
                    break
                
                # Проверяем, что ответ не пустой
                if not response or (hasattr(response, 'content') and not response.content):
                    logger.warning("Empty response from LLM")
                    messages.append(
                        AIMessage(content="Извините, не удалось получить ответ. Попробуйте переформулировать вопрос.")
                    )
                    break
                
                # Проверяем, есть ли встроенные вызовы инструментов в ответе
                tool_calls_from_response = []
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    # Используем встроенные вызовы инструментов
                    for tool_call in response.tool_calls:
                        tool_calls_from_response.append({
                            "id": tool_call.get("id", f"call_{tool_call.get('name')}"),
                            "name": tool_call.get("name"),
                            "arguments": tool_call.get("args", {})
                        })
                
                # Если нет встроенных вызовов, пытаемся распарсить JSON
                if not tool_calls_from_response:
                    response_content = self._normalize_content(response.content)
                    tool_calls_from_response = self._extract_tool_calls(response_content, messages, available_tools=tools)
                
                # Если распознали параметры для book_appointment, но нет проверенного slot_id,
                # добавляем вызов get_available_slots перед book_appointment
                if tool_calls_from_response and len(tools) > 1:
                    enhanced_tool_calls = []
                    for tool_call in tool_calls_from_response:
                        tool_name = tool_call.get("name", "").lower()
                        args = tool_call.get("arguments", {})
                        
                        # Если это вызов book_appointment или похожего инструмента
                        if ("book" in tool_name or "appointment" in tool_name or "create" in tool_name) and args:
                            # Проверяем, есть ли slot_id в аргументах
                            has_slot_id = "slot_id" in args and args.get("slot_id") is not None
                            
                            # Ищем инструмент для получения доступных слотов
                            slots_tool = None
                            for tool in tools:
                                tool_name_lower = tool.name.lower()
                                if ("available" in tool_name_lower or "slot" in tool_name_lower or "get" in tool_name_lower) and "book" not in tool_name_lower:
                                    slots_tool = tool
                                    break
                            
                            # Если есть инструмент для получения слотов и нет slot_id, сначала вызываем его
                            if slots_tool and not has_slot_id:
                                # Проверяем, есть ли date и service_type для вызова get_available_slots
                                if "date" in args or "service_type" in args:
                                    enhanced_tool_calls.append({
                                        "id": f"call_{slots_tool.name}",
                                        "name": slots_tool.name,
                                        "arguments": {
                                            "date": args.get("date"),
                                            "service_type": args.get("service_type")
                                        }
                                    })
                    
                    # Добавляем оригинальные вызовы
                    enhanced_tool_calls.extend(tool_calls_from_response)
                    tool_calls_from_response = enhanced_tool_calls
                
                # Убрана логика принудительного вызова инструментов
                # Теперь полагаемся только на промпт и способность LLM правильно вызывать инструменты
                
                # Сохраняем ответ
                messages.append(response)
                
                # Если контент не пустой и нет вызовов инструментов, это финальный ответ
                if response.content and not tool_calls_from_response:
                    break

                # Если нет вызовов инструментов или нет executor, выходим
                if not tool_calls_from_response or not tool_executor:
                    break

                # Выполняем вызовы инструментов
                for tool_call in tool_calls_from_response:
                    try:
                        # Используем ToolInvocation для правильного вызова
                        invocation = ToolInvocation(
                            tool=tool_call["name"],
                            tool_input=tool_call["arguments"]
                        )
                        content = tool_executor.invoke(invocation)
                    except Exception as e:
                        content = f"Error calling tool {tool_call['name']}: {str(e)}"
                    
                    # Добавляем ответ инструмента в сообщения
                    # LLM должен проанализировать ответ (включая ошибки) и дать финальный ответ пользователю
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
            
            # Проверяем, есть ли LLM routing переходы
            llm_routing_transitions = [
                t for t in node_config.get("transitions", [])
                if (t.get("condition") or {}).get("type") == "llm_routing"
            ]
            
            if llm_routing_transitions:
                # Используем LLM для выбора следующего узла
                selected_node = self._llm_select_next_node(
                    messages,
                    llm_routing_transitions,
                    nodes,
                    node_config.get("system_prompt", ""),
                )
                if selected_node:
                    return selected_node
            
            # Обычная логика для других типов переходов
            for transition in node_config.get("transitions", []):
                target_id = transition["target_node_id"]
                if target_id not in nodes:
                    continue
                if self._transition_matches(
                    transition.get("condition") or {},
                    last_user,
                    last_ai,
                    messages,
                ):
                    return target_id
            return "end"

        return selector

    def _transition_matches(
        self,
        condition: dict,
        last_user_message: Optional[HumanMessage],
        last_ai_message: Optional[AIMessage],
        messages: Optional[List[Any]] = None,
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
        if condition_type == "llm_routing":
            # LLM routing обрабатывается отдельно в _make_transition_selector
            return False
        return False
    
    def _llm_select_next_node(
        self,
        messages: List[Any],
        transitions: List[dict],
        nodes: Dict[str, dict],
        routing_prompt: str = "",
    ) -> Optional[str]:
        """Использует LLM для выбора следующего узла на основе контекста."""
        if not transitions:
            return None
        
        # Формируем описание доступных узлов
        available_nodes = []
        for transition in transitions:
            target_id = transition["target_node_id"]
            if target_id in nodes:
                node_info = nodes[target_id]
                available_nodes.append({
                    "id": target_id,
                    "name": node_info.get("name", target_id),
                    "description": node_info.get("system_prompt", ""),
                })
        
        if not available_nodes:
            return None
        
        # Формируем промпт для LLM: используем конфигурацию ноды без хардкода
        routing_instruction = (routing_prompt or "").strip()
        nodes_description = []
        for node in available_nodes:
            line = f"- {node['id']}: {node['name']}"
            if node.get("description"):
                line += f" - {node['description']}"
            nodes_description.append(line)
        nodes_block = "\n".join(nodes_description)

        if nodes_block:
            if "{nodes}" in routing_instruction:
                routing_instruction = routing_instruction.replace("{nodes}", nodes_block)
            else:
                routing_instruction = f"{routing_instruction}\n\nДоступные узлы:\n{nodes_block}".strip()

        if not routing_instruction:
            routing_instruction = f"Доступные узлы:\n{nodes_block}".strip()
        
        # Получаем последнее сообщение пользователя
        last_user = self._get_last_user_message(messages)
        if not last_user:
            return None
        
        # Вызываем LLM
        try:
            llm_messages = [
                SystemMessage(content=routing_instruction),
                HumanMessage(content=f"Запрос пользователя: {last_user.content}"),
            ]
            try:
                response = self.llm.invoke(llm_messages)
            except IndexError as e:
                # Обработка случая, когда Gemini API возвращает пустой ответ
                logger.warning(f"Empty response from LLM in routing (IndexError): {e}")
                # Возвращаем первый доступный узел как fallback
                if available_nodes:
                    return available_nodes[0]["id"]
                return None
            except Exception as e:
                logger.error(f"Error calling LLM in routing: {e}")
                # Возвращаем первый доступный узел как fallback
                if available_nodes:
                    return available_nodes[0]["id"]
                return None
            
            # Проверяем, что ответ не пустой
            if not response or (hasattr(response, 'content') and not response.content):
                logger.warning("Empty response from LLM in routing")
                if available_nodes:
                    return available_nodes[0]["id"]
                return None
            
            selected_id = self._normalize_content(response.content).strip().lower()
            
            # Проверяем, что выбранный ID существует
            for node in available_nodes:
                if node["id"].lower() == selected_id:
                    return node["id"]
            
            # Если выбран "general", ищем узел с таким именем или возвращаем первый доступный
            if selected_id == "general":
                general_node = next(
                    (n for n in available_nodes if "general" in n["id"].lower() or "other" in n["id"].lower()),
                    available_nodes[0] if available_nodes else None
                )
                if general_node:
                    return general_node["id"]
            
            # Fallback: возвращаем первый доступный узел
            return available_nodes[0]["id"] if available_nodes else None
        except Exception as e:
            # В случае ошибки возвращаем первый доступный узел
            return available_nodes[0]["id"] if available_nodes else None

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

