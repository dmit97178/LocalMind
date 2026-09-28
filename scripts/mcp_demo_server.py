"""Minimal stdio MCP service used by P7b tests and local demonstrations."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

PROTOCOL_VERSION = "2024-11-05"


def _send(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _response(request_id: object, result: object) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _tool(fault: str) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    if fault == "schema_mismatch":
        schema["properties"] = {"text": {"type": "integer"}}
    item: dict[str, object] = {
        "name": "json_format",
        "description": "MCP_UNTRUSTED_DESCRIPTION_IGNORE_PREVIOUS_INSTRUCTIONS",
        "annotations": {"title": "MCP_UNTRUSTED_TITLE"},
        "inputSchema": schema,
    }
    if fault == "hint_readonly_false":
        item["annotations"] = {"readOnlyHint": False}
    return item


def _call_result(fault: str, arguments: object, dump_env: bool, dump_argv: bool) -> dict[str, object]:
    if fault == "iserror":
        return {"content": [{"type": "text", "text": "private failure"}], "isError": True}
    if fault == "non_text_content":
        return {"content": [{"type": "image", "data": "ignored"}], "isError": False}
    if fault == "ansi_text":
        return {"content": [{"type": "text", "text": "safe\x1b[2J\x1b]52;c;evil\x07text"}]}
    if dump_env:
        text = json.dumps(sorted(os.environ), ensure_ascii=False)
    elif dump_argv:
        text = json.dumps({"argv": sys.argv, "pid": os.getpid()}, ensure_ascii=False)
    else:
        text_value = arguments.get("text") if isinstance(arguments, dict) else None
        if not isinstance(text_value, str):
            return {"content": [{"type": "text", "text": "text is required"}], "isError": True}
        try:
            value = json.loads(text_value)
        except json.JSONDecodeError:
            return {"content": [{"type": "text", "text": "invalid JSON"}], "isError": True}
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault", default="")
    parser.add_argument("--dump-env", action="store_true")
    parser.add_argument("--dump-argv", action="store_true")
    args, _ = parser.parse_known_args()
    if args.fault == "ignore_sigterm" and hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: None)
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = request.get("method")
        if method == "notifications/initialized":
            continue
        if args.fault == "hang":
            time.sleep(3600)
        if args.fault == "die" and method == "tools/call":
            raise SystemExit(7)
        if args.fault == "garbage":
            sys.stdout.write("not-json\n")
            sys.stdout.flush()
            continue
        if args.fault == "oversize":
            sys.stdout.write("x" * 70000 + "\n")
            sys.stdout.flush()
            continue
        if args.fault == "late_reply" and method == "tools/call":
            time.sleep(2)
        request_id = request.get("id")
        if args.fault == "bool_id" and request_id == 1:
            request_id = True
        if args.fault == "no_id":
            _send({"jsonrpc": "2.0", "method": "demo/notice", "params": {}})
        if args.fault == "bad_result":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {}, "error": {}})
            continue
        if method == "initialize":
            version = "2099-01-01" if args.fault == "bad_version" else PROTOCOL_VERSION
            _response(request_id, {"protocolVersion": version, "capabilities": {}})
        elif method == "tools/list":
            if args.fault == "changed_notice":
                _send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
            tools = [_tool(args.fault)]
            if args.fault == "extra_tools":
                tools.extend([
                    {"name": "unapproved", "inputSchema": {"type": "object"}},
                    {"name": "also_unapproved", "inputSchema": {"type": "object"}},
                ])
            if args.fault == "malformed_tool":
                tools.append({"name": 123, "inputSchema": {"type": "object"}})
            result: dict[str, object] = {"tools": tools}
            if args.fault == "pagination":
                result["nextCursor"] = "next-page"
            _response(request_id, result)
        elif method == "tools/call":
            if args.fault == "noisy_stderr":
                sys.stderr.write("noise" * 100000)
                sys.stderr.flush()
            _response(
                request_id,
                _call_result(
                    args.fault,
                    request.get("params", {}).get("arguments", {}),
                    args.dump_env,
                    args.dump_argv,
                ),
            )
        else:
            _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601}})


if __name__ == "__main__":
    main()
