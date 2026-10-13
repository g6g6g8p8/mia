"""Bounded, inert adapters for text and supported conversation exports.

These adapters preserve authorship separately from the rendered transcript. They
do not fetch links, execute imported instructions, or treat a source date as proof
that work is still current. Unsupported content is counted rather than retained.
"""

import codecs
import hashlib
import io
import json
import math
import re
from itertools import islice
from pathlib import PurePosixPath

PARSER_VERSION = "mia-migration-formats/1"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_EXPORT_BYTES = 100 * 1024 * 1024
STREAM_READ_BYTES = 64 * 1024
MAX_CONVERSATIONS = 10_000
MAX_NODES = 20_000
MAX_MESSAGES = 100_000


def _string(value, label, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label}: esperado texto")
    if "\x00" in value:
        raise ValueError(f"{label}: caractere nulo não permitido")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label}: Unicode inválido") from error
    return value


def _identifier(value, label):
    value = _string(value, label, optional=True)
    if value is not None and (not value or len(value) > 512):
        raise ValueError(f"{label}: identificador inválido")
    return value


def _date(value, label):
    if value is None:
        return None
    if isinstance(value, str):
        return _string(value, label)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{label}: data inválida")
        return value
    raise ValueError(f"{label}: data inválida")


def _dates(item):
    return {
        name: _date(item[name], name)
        for name in ("create_time", "update_time", "created_at", "updated_at")
        if name in item
    }


def _omissions():
    return {
        "attachments": 0,
        "tools": 0,
        "unsupported_parts": 0,
        "skipped_branches": 0,
        "skipped_messages": 0,
        "unknown_roles": 0,
        "empty_messages": 0,
    }


def _metadata(path, kind, conversation=None):
    source = {"path": path, "format": kind}
    if conversation is not None:
        source["dates"] = _dates(conversation)
        source["ids"] = {
            field: _identifier(conversation[field], field)
            for field in ("id", "uuid", "conversation_id")
            if field in conversation
        }
    return {
        "parser_version": PARSER_VERSION,
        "source": source,
        "messages": [],
        "omissions": _omissions(),
        "omission_units": {
            "attachments": "referências de anexos, não arquivos distintos",
            "tools": "mensagens ou partes de ferramentas não importadas",
            "unsupported_parts": "partes não textuais não importadas",
            "skipped_branches": "nós fora do ramo selecionado no export",
            "skipped_messages": "mensagens não importadas, inclusive fora do ramo",
        },
        "date_semantics": "datas declaradas na origem; não confirmam atualidade",
    }


def _source_id(kind, conversation, metadata):
    fields = ("uuid", "id", "conversation_id") if kind == "claude" else ("id", "conversation_id", "uuid")
    for field in fields:
        identifier = metadata["source"]["ids"].get(field)
        if identifier:
            metadata["source"]["id_origin"] = field
            return f"{kind}:{identifier}"
    # This fallback does not promise identity across edits. It is independent of
    # the conversation's position in the export and dictionary key ordering.
    canonical = json.dumps(conversation, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    metadata["source"]["id_origin"] = "derived-content"
    return f"{kind}:derived:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _attachment_count(item):
    count = 0
    for field in ("attachments", "files"):
        if field not in item or item[field] is None:
            continue
        if not isinstance(item[field], list):
            raise ValueError(f"{field}: esperado lista")
        count += len(item[field])
    return count


def _part_text(parts, omissions, *, claude=False):
    if not isinstance(parts, list):
        raise ValueError("Conteúdo da mensagem: esperado lista")
    text_parts = []
    supported_parts = []
    for part in parts:
        if isinstance(part, str) and not claude:
            text = _string(part, "Texto da mensagem")
            text_parts.append(text)
            supported_parts.append({"type": "text", "text": text})
        elif isinstance(part, dict):
            kind = part.get("type", part.get("content_type"))
            if kind == "text":
                text = _string(part.get("text"), "Parte textual")
                text_parts.append(text)
                supported_parts.append({"type": "text", "text": text})
            else:
                omissions["unsupported_parts"] += 1
                if isinstance(kind, str) and (kind.startswith("tool") or kind in ("code", "execution_output")):
                    omissions["tools"] += 1
                elif _attachment_type(kind):
                    omissions["attachments"] += 1
        else:
            raise ValueError("Parte de mensagem inválida")
    return "\n".join(text_parts), supported_parts


def _attachment_type(kind):
    return isinstance(kind, str) and any(word in kind.lower() for word in ("image", "audio", "video", "file", "attachment", "document"))


def _render(messages):
    return "\n\n".join(
        f"[{message['role']} · {next((v for k, v in message['dates'].items() if k in ('created_at', 'create_time') and v is not None), 'data não informada')}]\n{message['text']}"
        for message in messages
    )


def _title(conversation):
    value = conversation.get("title") or conversation.get("name") or "Conversa sem título"
    return _string(value, "Título da conversa")[:200]


def _validate_mapping(mapping):
    """Validate all parent chains, including omitted branches, in linear time."""
    done = set()
    for identifier, node in mapping.items():
        _identifier(identifier, "ID do nó")
        if not isinstance(node, dict):
            raise ValueError("Nó da conversa inválido")
        if node.get("id") is not None:
            _identifier(node["id"], "ID declarado do nó")
        parent = _identifier(node.get("parent"), "Nó pai")
        if parent is not None and parent not in mapping:
            raise ValueError("Árvore da conversa tem nó pai ausente")
        if "children" in node:
            children = node["children"]
            if not isinstance(children, list):
                raise ValueError("Filhos do nó: esperado lista")
            for child in children:
                _identifier(child, "ID de nó filho")
                if child not in mapping:
                    raise ValueError("Árvore da conversa tem nó filho ausente")
        if node.get("message") is not None and not isinstance(node["message"], dict):
            raise ValueError("Mensagem da conversa inválida")
    for identifier in mapping:
        chain = set()
        current = identifier
        while current is not None and current not in done:
            if current in chain:
                raise ValueError("Árvore da conversa contém ciclo")
            chain.add(current)
            current = mapping[current].get("parent")
        done.update(chain)


def _chatgpt(conversation, path):
    mapping = conversation["mapping"]
    _validate_mapping(mapping)
    current_node = _identifier(conversation.get("current_node"), "Ramo atual")
    if current_node is None or current_node not in mapping:
        raise ValueError("Ramo atual ausente na conversa ChatGPT")
    chain = []
    current = current_node
    while current is not None:
        chain.append(current)
        current = mapping[current].get("parent")
    chain.reverse()
    included = set(chain)
    metadata = _metadata(path, "chatgpt", conversation)
    omitted = sorted(identifier for identifier in mapping if identifier not in included)
    metadata["branch"] = {
        "current_node": current_node,
        "included_node_ids": chain,
        "omitted_node_ids": omitted,
    }
    omissions = metadata["omissions"]
    omissions["skipped_branches"] = len(omitted)
    for node_id, node in mapping.items():
        message = node.get("message")
        if message is None:
            continue
        # Validate structured fields even on omitted branches so a malformed
        # entry never appears to have been fully parsed.
        identifier = _identifier(message.get("id"), "ID da mensagem")
        dates = _dates(message)
        author = message.get("author", {})
        if not isinstance(author, dict):
            raise ValueError("Autoria da mensagem inválida")
        role = author.get("role", "unknown")
        _string(role, "Papel da mensagem")
        content = message.get("content", {})
        if not isinstance(content, dict):
            raise ValueError("Conteúdo da mensagem inválido")
        extra = message.get("metadata", {})
        if extra is None:
            extra = {}
        if not isinstance(extra, dict):
            raise ValueError("Metadados da mensagem inválidos")
        omissions["attachments"] += _attachment_count(extra) + _attachment_count(message)
        content_type = content.get("content_type", "text")
        if not isinstance(content_type, str):
            raise ValueError("Tipo do conteúdo inválido")
        local_omissions = _omissions()
        text, parts = _part_text(content.get("parts", []), local_omissions)
        for counter in ("attachments", "unsupported_parts", "tools"):
            omissions[counter] += local_omissions[counter]
        if content_type not in ("text", "multimodal_text"):
            omissions["unsupported_parts"] += 1
            if content_type in ("code", "execution_output"):
                omissions["tools"] += 1
            elif _attachment_type(content_type):
                omissions["attachments"] += 1
            text = ""
        recipient = message.get("recipient")
        is_tool = role == "tool" or (recipient is not None and recipient != "all") or content_type in ("code", "execution_output")
        if is_tool:
            if not local_omissions["tools"] and content_type not in ("code", "execution_output"):
                omissions["tools"] += 1
        if role not in ("user", "assistant", "tool"):
            omissions["unknown_roles"] += 1
        if node_id not in included:
            omissions["skipped_messages"] += 1
            continue
        if is_tool:
            omissions["skipped_messages"] += 1
            continue
        if role not in ("user", "assistant"):
            omissions["skipped_messages"] += 1
            continue
        if not text.strip():
            omissions["empty_messages"] += 1
            omissions["skipped_messages"] += 1
            continue
        preserved = {
            "id": identifier,
            "node_id": node_id,
            "parent_id": node.get("parent"),
            "role": role,
            "original_role": role,
            "text": text,
            "text_parts": parts,
            "dates": dates,
            "content_type": content_type,
        }
        if author.get("name") is not None:
            preserved["author_name"] = _string(author["name"], "Nome do autor")
        metadata["messages"].append(preserved)
    by_node = {message["node_id"]: message for message in metadata["messages"]}
    metadata["messages"] = [by_node[node_id] for node_id in chain if node_id in by_node]
    if not metadata["messages"]:
        raise ValueError("Conversa sem mensagens textuais legíveis")
    return {
        "title": _title(conversation),
        "kind": "chatgpt",
        "content": _render(metadata["messages"]),
        "source_id": _source_id("chatgpt", conversation, metadata),
        "metadata": metadata,
    }


def _claude(conversation, path):
    metadata = _metadata(path, "claude", conversation)
    omissions = metadata["omissions"]
    for message in conversation["chat_messages"]:
        if not isinstance(message, dict):
            raise ValueError("Mensagem Claude inválida")
        identifier = _identifier(message.get("uuid", message.get("id")), "ID da mensagem")
        dates = _dates(message)
        sender = message.get("sender", "unknown")
        _string(sender, "Papel da mensagem")
        omissions["attachments"] += _attachment_count(message)
        exported_text = _string(message.get("text"), "Texto da mensagem", optional=True)
        content = message.get("content")
        if content is not None:
            text, parts = _part_text(content, omissions, claude=True)
            if not content and exported_text is not None:
                text = exported_text
        else:
            text, parts = exported_text or "", []
        role = {"human": "user", "user": "user", "assistant": "assistant"}.get(sender)
        if role is None:
            omissions["tools" if sender in ("tool", "tool_result") else "unknown_roles"] += 1
            omissions["skipped_messages"] += 1
            continue
        if not text.strip():
            omissions["empty_messages"] += 1
            omissions["skipped_messages"] += 1
            continue
        preserved = {
            "id": identifier,
            "role": role,
            "original_role": sender,
            "text": text,
            "text_parts": parts,
            "dates": dates,
        }
        if exported_text is not None:
            preserved["exported_text"] = exported_text
        metadata["messages"].append(preserved)
    if not metadata["messages"]:
        raise ValueError("Conversa sem mensagens textuais legíveis")
    return {
        "title": _title(conversation),
        "kind": "claude",
        "content": _render(metadata["messages"]),
        "source_id": _source_id("claude", conversation, metadata),
        "metadata": metadata,
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _string(key, "Chave JSON")
        if key in result:
            raise ValueError("JSON contém chaves repetidas")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("JSON contém número não finito")


def _parse_json(text):
    try:
        data = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("JSON inválido ou profundo demais") from error
    # JSON's escaped strings and exponent notation also need validation. For
    # example, json.loads accepts a lone escaped surrogate and makes 1e400 inf.
    pending = [data]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str):
            _string(value, "Texto JSON")
        elif isinstance(value, float) and not math.isfinite(value):
            _invalid_constant(value)
    return data


def _records(conversations, path):
    nodes = messages = 0
    seen = set()
    count = 0
    for conversation in conversations:
        count += 1
        if count > MAX_CONVERSATIONS:
            raise ValueError(f"Exportação excede {MAX_CONVERSATIONS} conversas")
        if not isinstance(conversation, dict):
            raise ValueError("Conversa inválida")
        if "mapping" in conversation and "chat_messages" in conversation:
            raise ValueError("Formato de conversa ambíguo")
        if isinstance(conversation.get("mapping"), dict):
            mapping = conversation["mapping"]
            nodes += len(mapping)
            messages += sum(isinstance(node, dict) and node.get("message") is not None for node in mapping.values())
            del mapping
            adapter = _chatgpt
        elif isinstance(conversation.get("chat_messages"), list):
            messages += len(conversation["chat_messages"])
            adapter = _claude
        else:
            raise ValueError("Formato JSON não reconhecido; use exportação ChatGPT/Claude, Markdown ou texto")
        if nodes > MAX_NODES:
            raise ValueError(f"Exportação excede {MAX_NODES} nós de conversa")
        if messages > MAX_MESSAGES:
            raise ValueError(f"Exportação excede {MAX_MESSAGES} mensagens")
        record = adapter(conversation, path)
        if record["source_id"] in seen:
            raise ValueError("Exportação contém identificadores de conversa repetidos")
        seen.add(record["source_id"])
        yield record
        # The next iteration must not retain the previous parsed conversation.
        del record, conversation
    if not count:
        raise ValueError("Esperada lista não vazia de conversas ChatGPT ou Claude")


def _conversations(text, path):
    data = _parse_json(text)
    if not isinstance(data, list):
        raise ValueError("Esperada lista não vazia de conversas ChatGPT ou Claude")
    # The compatibility API still returns only after the whole file succeeds.
    return list(_records(data, path))


def _chunks(stream, limit):
    received = 0
    while True:
        raw = stream.read(STREAM_READ_BYTES)
        if not isinstance(raw, bytes) or len(raw) > STREAM_READ_BYTES:
            raise ValueError("Conteúdo: esperado fluxo binário com leitura limitada")
        if not raw:
            return
        received += len(raw)
        if received > limit:
            if limit == MAX_EXPORT_BYTES:
                raise ValueError("Exportação excede 100 MiB")
            raise ValueError("Arquivo excede 8 MiB")
        yield raw


def _iter_json_objects(stream):
    """Scan the top-level array once, parsing only complete conversation objects.

    No fragment is reparsed to detect completion. Incremental UTF-8 decoding
    handles split codepoints/BOMs; the lexical scan handles split escapes and
    brackets inside strings. Each object is independently bounded to 8 MiB.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    state = "start"
    fragments = []
    received = 0
    stack = []
    quoted = escaped = False

    def append(fragment):
        nonlocal received
        received += len(fragment.encode("utf-8"))
        if received > MAX_FILE_BYTES:
            raise ValueError("Conversa excede 8 MiB")
        fragments.append(fragment)

    def decoded_chunks():
        try:
            for raw in _chunks(stream, MAX_EXPORT_BYTES):
                yield decoder.decode(raw)
            tail = decoder.decode(b"", final=True)
            if tail:
                yield tail
        except UnicodeDecodeError as error:
            raise ValueError("Arquivo não é texto UTF-8 válido") from error

    for text in decoded_chunks():
        if "\x00" in text:
            raise ValueError("Arquivo binário não suportado")
        segment_start = 0 if state == "object" else None
        for position, char in enumerate(text):
            if state != "object":
                if char in " \t\r\n":
                    continue
                if state == "start" and char == "[":
                    state = "first"
                    continue
                if state in ("first", "next") and char == "{":
                    state = "object"
                    stack = ["}"]
                    quoted = escaped = False
                    segment_start = position
                    continue
                if state == "first" and char == "]":
                    raise ValueError("Esperada lista não vazia de conversas ChatGPT ou Claude")
                if state == "separator" and char == ",":
                    state = "next"
                    continue
                if state == "separator" and char == "]":
                    state = "complete"
                    continue
                raise ValueError("JSON inválido: lista, separador ou fim de arquivo incorreto")
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "{[":
                stack.append("}" if char == "{" else "]")
                if len(stack) > 1024:
                    raise ValueError("JSON inválido ou profundo demais")
            elif char in "}]":
                if not stack or char != stack.pop():
                    raise ValueError("JSON inválido: delimitadores incompatíveis")
                if not stack:
                    append(text[segment_start:position + 1])
                    conversation = _parse_json("".join(fragments))
                    fragments = []
                    received = 0
                    segment_start = None
                    state = "separator"
                    yield conversation
                    del conversation
        if segment_start is not None:
            append(text[segment_start:])
    if state != "complete":
        raise ValueError("JSON inválido ou incompleto")


def iter_entry(path: str, stream):
    """Yield records from a bounded binary stream, including 100 MiB exports.

    A later syntax/limit error can follow earlier yielded records. Callers MUST
    stage a file's records privately and publish only after this generator has
    exhausted successfully; closing early is not a valid completed import.
    Markdown/text remains bounded to 8 MiB. JSON keeps at most one conversation
    in parser memory, with export-wide resource and duplicate-identity limits.
    """
    _string(path, "Caminho")
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".json":
        yield from _records(_iter_json_objects(stream), path)
    elif suffix in (".md", ".markdown", ".txt"):
        yield from decode_entry(path, b"".join(_chunks(stream, MAX_FILE_BYTES)))
    else:
        raise ValueError("Use Markdown, texto ou JSON de conversas")


def _declared_dates(text):
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}
    dates = {}
    for line in islice(io.StringIO(text), 1, 64):
        if line.strip() in ("---", "..."):
            return dates
        match = re.fullmatch(r"(date|created|updated|created_at|updated_at):\s*['\"]?(\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+Z-]+)?)['\"]?\s*", line)
        if match:
            dates[match[1]] = match[2]
    return {}


def decode_entry(path: str, raw: bytes) -> list[dict]:
    """Decode one entry atomically; malformed/unsupported entries raise ValueError."""
    _string(path, "Caminho")
    if not isinstance(raw, bytes):
        raise ValueError("Conteúdo: esperado bytes")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Arquivo excede 8 MiB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Arquivo não é texto UTF-8 válido") from error
    if "\x00" in text:
        raise ValueError("Arquivo binário não suportado")
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".json":
        return _conversations(text, path)
    if suffix not in (".md", ".markdown", ".txt"):
        raise ValueError("Use Markdown, texto ou JSON de conversas")
    if not text.strip():
        raise ValueError("Arquivo vazio")
    title = PurePosixPath(path).stem[:200]
    for line in io.StringIO(text):
        match = re.match(r"^#{1,6}[ \t]+", line)
        if match and line[match.end():].strip():
            title = line[match.end():].strip().rstrip("#").strip()[:200]
            break
    kind = "markdown" if suffix in (".md", ".markdown") else "text"
    metadata = _metadata(path, kind)
    metadata["source"]["id_origin"] = "path"
    metadata["source"]["declared_dates"] = _declared_dates(text)
    metadata["source"]["received_bytes"] = len(raw)
    return [{"title": title, "kind": kind, "content": text, "source_id": "file:" + path, "metadata": metadata}]
