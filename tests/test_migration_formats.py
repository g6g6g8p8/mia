import io
import json

import pytest

from mia import migration_formats as formats


def encode(conversations):
    return json.dumps(conversations).encode()


def chatgpt(identifier="conversation-1", title="Projeto reconhecível"):
    return {
        "id": identifier,
        "title": title,
        "create_time": 1_700_000_000,
        "update_time": 1_700_000_100,
        "current_node": "assistant-node",
        "mapping": {
            "root": {"parent": None, "message": None},
            "user-node": {
                "parent": "root",
                "message": {
                    "id": "message-user",
                    "author": {"role": "user", "name": "Pessoa"},
                    "create_time": 1_700_000_001,
                    "content": {"content_type": "text", "parts": ["Qual decisão foi tomada?"]},
                },
            },
            "assistant-node": {
                "parent": "user-node",
                "message": {
                    "id": "message-assistant",
                    "author": {"role": "assistant"},
                    "create_time": 1_700_000_002,
                    "update_time": 1_700_000_003,
                    "content": {"content_type": "text", "parts": ["Esta é uma resposta antiga da IA."]},
                },
            },
        },
    }


def claude(identifier="claude-1"):
    return {
        "uuid": identifier,
        "name": "Decisão Claude",
        "created_at": "2025-01-01T10:00:00Z",
        "updated_at": "2025-01-01T10:02:00Z",
        "chat_messages": [
            {"uuid": "human-1", "sender": "human", "created_at": "2025-01-01T10:00:00Z", "text": "Minha pergunta"},
            {"uuid": "assistant-1", "sender": "assistant", "created_at": "2025-01-01T10:01:00Z", "content": [{"type": "text", "text": "Uma hipótese do assistente"}]},
        ],
    }


def test_long_markdown_preserves_tail_and_declared_date_without_mtime():
    text = "---\ncreated: '2020-02-03'\n---\n# Trabalho original\n" + "Trecho grande. " * 20_000 + "\nDECISÃO SOMENTE NO FINAL"
    result = formats.decode_entry("projetos/longo.md", text.encode())[0]
    assert len(result["content"]) > 200_000
    assert result["content"] == text
    assert result["content"].endswith("DECISÃO SOMENTE NO FINAL")
    assert result["title"] == "Trabalho original"
    assert result["source_id"] == "file:projetos/longo.md"
    assert result["metadata"]["source"]["declared_dates"] == {"created": "2020-02-03"}
    assert "mtime" not in json.dumps(result["metadata"])
    assert result["metadata"]["parser_version"] == formats.PARSER_VERSION


def test_bom_and_plain_text_keep_exact_source_text():
    result = formats.decode_entry("pasta/nota.TXT", b"\xef\xbb\xbfSem heading\nLinha final\n")[0]
    assert result["kind"] == "text"
    assert result["title"] == "nota"
    assert result["content"] == "Sem heading\nLinha final\n"
    assert result["metadata"]["source"]["received_bytes"] == 27


def test_chatgpt_authorship_ids_dates_and_branch_are_structured():
    conversation = chatgpt()
    # A JSON mapping can be serialized in any dictionary order.
    conversation["mapping"] = dict(reversed(list(conversation["mapping"].items())))
    item = formats.decode_entry("conversations.json", encode([conversation]))[0]
    assert item["source_id"] == "chatgpt:conversation-1"
    metadata = item["metadata"]
    assert metadata["source"]["dates"]["create_time"] == 1_700_000_000
    assert metadata["branch"]["included_node_ids"] == ["root", "user-node", "assistant-node"]
    assert [message["role"] for message in metadata["messages"]] == ["user", "assistant"]
    assert metadata["messages"][0]["id"] == "message-user"
    assert metadata["messages"][0]["node_id"] == "user-node"
    assert metadata["messages"][0]["author_name"] == "Pessoa"
    assert metadata["messages"][1]["dates"]["update_time"] == 1_700_000_003
    assert "[assistant ·" in item["content"]
    assert metadata["messages"][1]["text"] == "Esta é uma resposta antiga da IA."


def test_export_source_ids_survive_reordered_export_and_renamed_file():
    original = [chatgpt("first"), claude("second")]
    before = formats.decode_entry("primeiro.json", encode(original))
    after = formats.decode_entry("renomeado.json", encode(list(reversed(original))))
    assert {item["source_id"] for item in before} == {item["source_id"] for item in after}
    assert before[0]["source_id"] == after[1]["source_id"] == "chatgpt:first"
    assert before[1]["source_id"] == after[0]["source_id"] == "claude:second"


def test_derived_ids_are_explicit_and_independent_of_export_position():
    no_id = chatgpt()
    del no_id["id"]
    other = chatgpt("other")
    before = formats.decode_entry("export.json", encode([no_id, other]))[0]
    after = formats.decode_entry("export.json", encode([other, no_id]))[1]
    assert before["source_id"] == after["source_id"]
    assert before["source_id"].startswith("chatgpt:derived:")
    assert before["metadata"]["source"]["id_origin"] == "derived-content"


def test_branch_attachments_tools_unknown_roles_and_empty_messages_are_reported():
    conversation = chatgpt()
    mapping = conversation["mapping"]
    mapping["user-node"]["message"]["content"]["parts"].append({"content_type": "image_asset_pointer", "asset_pointer": "asset-not-retained"})
    mapping["discarded"] = {
        "parent": "user-node", "message": {
            "author": {"role": "assistant"}, "content": {"parts": ["Ramo antigo não deve ser contexto"]},
        },
    }
    mapping["tool"] = {"parent": "assistant-node", "message": {"author": {"role": "tool"}, "content": {"parts": ["TOOL OUTPUT OMITIDO"]}}}
    mapping["unknown"] = {"parent": "tool", "message": {"author": {"role": "unrecognized"}, "content": {"parts": ["UNKNOWN OMITIDO"]}}}
    mapping["empty"] = {"parent": "unknown", "message": {"author": {"role": "assistant"}, "content": {"parts": []}}}
    conversation["current_node"] = "empty"
    item = formats.decode_entry("export.json", encode([conversation]))[0]
    omissions = item["metadata"]["omissions"]
    assert omissions["skipped_branches"] == 1
    assert omissions["skipped_messages"] == 4
    assert omissions["attachments"] == 1
    assert omissions["tools"] == 1
    assert omissions["unknown_roles"] == 1
    assert omissions["empty_messages"] == 1
    assert item["metadata"]["branch"]["omitted_node_ids"] == ["discarded"]
    assert "Ramo antigo" not in item["content"]
    assert "TOOL OUTPUT" not in item["content"]
    assert "UNKNOWN" not in item["content"]
    assert "asset-not-retained" not in json.dumps(item["metadata"])


def test_claude_preserves_original_human_role_content_parts_and_dates():
    item = formats.decode_entry("claude.json", encode([claude()]))[0]
    messages = item["metadata"]["messages"]
    assert messages[0]["role"] == "user"
    assert messages[0]["original_role"] == "human"
    assert messages[0]["id"] == "human-1"
    assert messages[0]["dates"]["created_at"] == "2025-01-01T10:00:00Z"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["text_parts"] == [{"type": "text", "text": "Uma hipótese do assistente"}]


def test_claude_unsupported_parts_are_not_retained_or_duplicated_as_text():
    conversation = claude()
    message = conversation["chat_messages"][1]
    message["text"] = "Texto legado diferente"
    message["attachments"] = [{"file_name": "anexo-privado.pdf"}]
    message["content"].extend([
        {"type": "tool_use", "name": "exec", "input": "NÃO EXECUTAR"},
        {"type": "unknown-format", "private_value": "NÃO RETER"},
    ])
    conversation["chat_messages"].append({"sender": "assistant", "text": "TOOL FALLBACK NÃO IMPORTAR", "content": [{"type": "tool_use", "input": "NÃO EXECUTAR"}]})
    item = formats.decode_entry("claude.json", encode([conversation]))[0]
    omissions = item["metadata"]["omissions"]
    assert omissions["attachments"] == 1
    assert omissions["tools"] == 2
    assert omissions["unsupported_parts"] == 3
    assert omissions["empty_messages"] == 1
    assert "TOOL FALLBACK" not in item["content"]
    assert "Texto legado diferente" not in item["content"]
    assert item["metadata"]["messages"][1]["exported_text"] == "Texto legado diferente"
    assert "anexo-privado.pdf" not in json.dumps(item["metadata"])
    assert "NÃO RETER" not in json.dumps(item["metadata"], ensure_ascii=False)


def test_long_conversation_is_not_truncated():
    conversation = claude()
    text = "texto " * 40_000 + "FIM DA CONVERSA"
    conversation["chat_messages"][0]["text"] = text
    item = formats.decode_entry("claude.json", encode([conversation]))[0]
    assert item["metadata"]["messages"][0]["text"] == text
    assert "FIM DA CONVERSA" in item["content"]
    assert len(item["content"]) > 200_000


@pytest.mark.parametrize("raw", [b'{"email":"not-an-export"}', b"[]", b"[null]", b"[{\"chat_messages\":\"wrong\"}]", b"[{\"chat_messages\": []}]", b"[", b"\xff", b"[NaN]"])
def test_unrecognized_invalid_or_empty_json_is_rejected(raw):
    with pytest.raises(ValueError):
        formats.decode_entry("export.json", raw)


def test_duplicate_json_keys_are_not_silently_overwritten():
    with pytest.raises(ValueError, match="chaves repetidas"):
        formats.decode_entry("export.json", b'[{"id":"first","id":"second","chat_messages":[]}]')


@pytest.mark.parametrize("malformation", ["cycle", "missing-parent", "bad-message", "bad-parts", "bad-date", "surrogate"])
def test_malformed_conversation_rejects_whole_file_including_previous_valid_entry(malformation):
    broken = chatgpt("broken")
    node = broken["mapping"]["assistant-node"]
    if malformation == "cycle":
        node["parent"] = "assistant-node"
    elif malformation == "missing-parent":
        node["parent"] = "not-in-export"
    elif malformation == "bad-message":
        node["message"] = "wrong-type"
    elif malformation == "bad-parts":
        node["message"]["content"]["parts"] = "wrong-type"
    elif malformation == "bad-date":
        node["message"]["create_time"] = {"not": "date"}
    else:
        node["message"]["content"]["parts"] = ["\ud800"]
    with pytest.raises(ValueError):
        formats.decode_entry("export.json", encode([claude(), broken]))


def test_cycle_on_omitted_branch_is_still_rejected():
    conversation = chatgpt()
    conversation["mapping"]["not-selected"] = {"parent": "not-selected", "message": None}
    with pytest.raises(ValueError, match="ciclo"):
        formats.decode_entry("export.json", encode([conversation]))


def test_missing_current_branch_is_not_guessed():
    conversation = chatgpt()
    del conversation["current_node"]
    with pytest.raises(ValueError, match="Ramo atual"):
        formats.decode_entry("export.json", encode([conversation]))


def test_limits_apply_to_entire_export_not_per_conversation(monkeypatch):
    monkeypatch.setattr(formats, "MAX_CONVERSATIONS", 1)
    with pytest.raises(ValueError, match="conversas"):
        formats.decode_entry("export.json", encode([claude("one"), claude("two")]))
    monkeypatch.setattr(formats, "MAX_CONVERSATIONS", 10_000)
    monkeypatch.setattr(formats, "MAX_NODES", 5)
    with pytest.raises(ValueError, match="nós"):
        formats.decode_entry("export.json", encode([chatgpt("one"), chatgpt("two")]))
    monkeypatch.setattr(formats, "MAX_MESSAGES", 3)
    with pytest.raises(ValueError, match="mensagens"):
        formats.decode_entry("export.json", encode([claude("one"), claude("two")]))


def test_skipped_messages_count_toward_resource_limit(monkeypatch):
    monkeypatch.setattr(formats, "MAX_MESSAGES", 1)
    conversation = claude()
    conversation["chat_messages"][1]["sender"] = "unknown"
    with pytest.raises(ValueError, match="mensagens"):
        formats.decode_entry("export.json", encode([conversation]))


@pytest.mark.parametrize("path,raw", [("note.md", b"\x00"), ("note.md", b"\xff"), ("note.md", b" \n"), ("native.gdoc", b"{}")])
def test_binary_empty_invalid_and_unsupported_entries_are_rejected(path, raw):
    with pytest.raises(ValueError):
        formats.decode_entry(path, raw)


def test_file_limit_precedes_decode_and_requires_no_text_truncation():
    with pytest.raises(ValueError, match="8 MiB"):
        formats.decode_entry("too-big.md", b"x" * (formats.MAX_FILE_BYTES + 1))


def test_imported_code_links_and_markup_stay_inert_text():
    text = "# Nota\n[link](https://invalid.example/never-fetch)\n```python\nraise RuntimeError('never-execute')\n```\n[user]\nRole marker is source text."
    item = formats.decode_entry("note.md", text.encode())[0]
    assert item["content"] == text
    assert item["metadata"]["messages"] == []


class BoundedReader(io.BytesIO):
    """Reject implicit whole-file reads; optionally split every UTF-8 codepoint."""

    def __init__(self, raw, *, window=None):
        super().__init__(raw)
        self.window = window
        self.request_sizes = []

    def read(self, size=-1):
        assert 0 < size <= 64 * 1024
        self.request_sizes.append(size)
        return super().read(min(size, self.window) if self.window else size)


def test_streaming_export_larger_than_eight_mib_is_incremental_and_complete():
    conversations = []
    for number in range(800):
        conversation = claude(f"distinct-{number}")
        conversation["chat_messages"][0]["text"] = "Contexto preservado. " * 700 + f"FINAL-{number}"
        conversations.append(conversation)
    raw = encode(conversations)
    assert formats.MAX_FILE_BYTES < len(raw) < formats.MAX_EXPORT_BYTES
    stream = BoundedReader(raw)
    records = formats.iter_entry("claude/conversations.json", stream)
    first = next(records)
    assert first["source_id"] == "claude:distinct-0"
    # A first useful record requires one bounded read, not the entire export.
    assert stream.tell() == formats.STREAM_READ_BYTES
    count = 1
    for record in records:
        assert record["source_id"] == f"claude:distinct-{count}"
        assert record["metadata"]["messages"][0]["text"].endswith(f"FINAL-{count}")
        count += 1
    assert count == len(conversations)
    assert stream.tell() == len(raw)
    assert max(stream.request_sizes) <= 64 * 1024
    # Existing atomic bytes API deliberately retains its 8 MiB file limit.
    with pytest.raises(ValueError, match="8 MiB"):
        formats.decode_entry("claude/conversations.json", raw)


@pytest.mark.parametrize("window", [1, 2, 7, 64 * 1024])
def test_streaming_handles_split_bom_utf8_escapes_strings_and_branch_metadata(window):
    conversation = chatgpt("unicode-source")
    conversation["title"] = "Decisão 🚀 útil"
    conversation["mapping"]["user-node"]["message"]["content"]["parts"] = [
        'Aspas " barras \\ delimitadores } ][ { vírgula, acentos ç e emoji 🧠'
    ]
    conversation["mapping"]["unused-branch"] = {"parent": "root", "message": None}
    conversation["mapping"]["tool-node"] = {
        "parent": "assistant-node",
        "message": {"author": {"role": "tool"}, "content": {"parts": ["NÃO RETER"]}},
    }
    conversation["current_node"] = "tool-node"
    raw = b"\xef\xbb\xbf" + json.dumps([conversation, claude()], ensure_ascii=False).encode()
    actual = list(formats.iter_entry("export.json", BoundedReader(raw, window=window)))
    assert actual == formats.decode_entry("export.json", raw)
    assert actual[0]["metadata"]["omissions"]["tools"] == 1
    assert actual[0]["metadata"]["omissions"]["skipped_branches"] == 1
    assert "NÃO RETER" not in actual[0]["content"]


@pytest.mark.parametrize("path", ["note.md", "note.markdown", "note.txt"])
def test_streaming_text_and_markdown_preserve_exact_content(path):
    raw = b"\xef\xbb\xbf# Fonte antiga\nFinal preservado\n"
    assert list(formats.iter_entry(path, BoundedReader(raw, window=2))) == formats.decode_entry(path, raw)


def test_streaming_conversation_identity_is_stable_after_reordering_and_file_rename():
    conversations = [chatgpt("first"), claude("second")]
    before = list(formats.iter_entry("before.json", BoundedReader(encode(conversations))))
    after = list(formats.iter_entry("after.json", BoundedReader(encode(conversations[::-1]))))
    assert [record["source_id"] for record in before] == [record["source_id"] for record in after[::-1]]
    no_id = chatgpt()
    del no_id["id"]
    first = list(formats.iter_entry("a.json", BoundedReader(encode([no_id, claude()]))))[0]
    last = list(formats.iter_entry("b.json", BoundedReader(encode([claude(), no_id]))))[1]
    assert first["source_id"] == last["source_id"]
    assert first["metadata"]["source"]["id_origin"] == "derived-content"


def test_streaming_duplicate_identity_rejects_file_after_first_staged_record():
    records = formats.iter_entry("export.json", BoundedReader(encode([claude(), claude()])))
    assert next(records)["source_id"] == "claude:claude-1"
    with pytest.raises(ValueError, match="identificadores.*repetidos"):
        list(records)


@pytest.mark.parametrize("tail", [b",]", b",,]", b"][]", b"]null", b"]\xc2", b"]\x00", b",", b"", b",{\"id\":\"a\",\"id\":\"b\"}]", b",{\"x\":NaN}]"])
def test_streaming_invalid_tail_requires_caller_to_discard_prior_staged_records(tail):
    first = json.dumps(claude()).encode()
    records = formats.iter_entry("export.json", BoundedReader(b"[" + first + tail, window=1))
    assert next(records)["source_id"] == "claude:claude-1"
    with pytest.raises(ValueError):
        list(records)


@pytest.mark.parametrize("raw", [b"[]", b"{}", b"[null]", b"[,]", b"[\xff]", b"[{}]", b"[", b""])
def test_streaming_invalid_or_unrecognized_array_is_rejected(raw):
    with pytest.raises(ValueError):
        list(formats.iter_entry("export.json", BoundedReader(raw, window=1)))


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "\ud800", "\u0000"])
def test_streaming_rejects_invalid_unicode_or_nonfinite_numbers_even_in_unused_fields(value):
    conversation = claude()
    conversation["unused"] = value
    with pytest.raises(ValueError):
        list(formats.iter_entry("export.json", BoundedReader(encode([conversation]))))


def test_exponent_overflow_is_rejected_in_both_json_apis():
    raw = encode([claude()]).replace(b'"name":', b'"unused":1e400,"name":')
    with pytest.raises(ValueError, match="não finito"):
        list(formats.iter_entry("export.json", BoundedReader(raw)))
    with pytest.raises(ValueError, match="não finito"):
        formats.decode_entry("export.json", raw)


def test_streaming_per_conversation_limit_counts_raw_utf8_bytes(monkeypatch):
    conversation = claude()
    conversation["chat_messages"][0]["text"] = "🧠" * 100
    object_raw = json.dumps(conversation, ensure_ascii=False).encode()
    raw = b"[" + object_raw + b"]"
    monkeypatch.setattr(formats, "MAX_FILE_BYTES", len(object_raw))
    assert len(list(formats.iter_entry("export.json", BoundedReader(raw, window=7)))) == 1
    monkeypatch.setattr(formats, "MAX_FILE_BYTES", len(object_raw) - 1)
    with pytest.raises(ValueError, match="Conversa excede"):
        list(formats.iter_entry("export.json", BoundedReader(raw, window=7)))


def test_streaming_export_limit_counts_bom_and_whitespace(monkeypatch):
    raw = b"\xef\xbb\xbf" + encode([claude()]) + b" \n"
    monkeypatch.setattr(formats, "MAX_EXPORT_BYTES", len(raw))
    assert len(list(formats.iter_entry("export.json", BoundedReader(raw, window=7)))) == 1
    monkeypatch.setattr(formats, "MAX_EXPORT_BYTES", len(raw) - 1)
    with pytest.raises(ValueError, match="100 MiB"):
        list(formats.iter_entry("export.json", BoundedReader(raw, window=7)))


def test_streaming_text_keeps_eight_mib_limit(monkeypatch):
    monkeypatch.setattr(formats, "MAX_FILE_BYTES", 7)
    with pytest.raises(ValueError, match="8 MiB"):
        list(formats.iter_entry("note.markdown", BoundedReader(b"12345678", window=2)))


@pytest.mark.parametrize("limit,conversations", [("MAX_CONVERSATIONS", [claude("one"), claude("two")]), ("MAX_MESSAGES", [claude("one"), claude("two")]), ("MAX_NODES", [chatgpt("one"), chatgpt("two")])])
def test_streaming_global_resource_limits_do_not_reset_per_conversation(monkeypatch, limit, conversations):
    maximum = {"MAX_CONVERSATIONS": 1, "MAX_MESSAGES": 3, "MAX_NODES": 5}[limit]
    monkeypatch.setattr(formats, limit, maximum)
    records = formats.iter_entry("export.json", BoundedReader(encode(conversations)))
    next(records)
    with pytest.raises(ValueError, match="Exportação excede"):
        list(records)


def test_streaming_rejects_overdeep_json_without_recursion_crash():
    raw = b'[{"unused":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}]"
    with pytest.raises(ValueError, match="profundo demais"):
        list(formats.iter_entry("export.json", BoundedReader(raw)))
