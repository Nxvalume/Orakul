"""Regression tests for ChatGPT widget's delayed MCP session delivery."""
import re
import shutil
import subprocess

import pytest

from chat_ui import CHAT_HTML


def test_inline_view_can_use_delayed_chatgpt_globals_and_mcp_text():
    assert "window.addEventListener('openai:set_globals'" in CHAT_HTML
    assert "globals.toolInput" in CHAT_HTML
    assert "globals.toolOutput" in CHAT_HTML
    assert "const next=sessionFrom(payload);" in CHAT_HTML
    assert "const images=Array.isArray(sr?.content)" in CHAT_HTML
    assert "Array.isArray(sr?.content_items)" in CHAT_HTML
    assert "ChatGPT не передал изображение браузера" in CHAT_HTML
    assert "ChatGPT не передал ID браузера" in CHAT_HTML


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js unavailable")
def test_mcp_session_id_parsed_from_actual_wire_envelopes():
    match = re.search(
        r"(?ms)^ function sessionFrom\(payload,depth=0\)\{.*?^ \}\n function inputFrom",
        CHAT_HTML,
    )
    assert match is not None
    js = match.group(0).rsplit("\n function inputFrom", 1)[0]
    # All of these are valid variants emitted by real MCP Apps hosts/adapters.
    script = js + """
const sid='db375391-69d6-4cdd-9df5-7ff6606dbd3e';
const cases=[
 {session_id:sid},
 {arguments:{session_id:sid}},
 {structuredContent:{session_id:sid}},
 {content:[{type:'text',text:JSON.stringify({session_id:sid})}]},
 {result:{content:[{type:'text',text:JSON.stringify({session_id:sid})}]}},
 {content_items:[{type:'text',text:JSON.stringify({session_id:sid})}]},
 {text:JSON.stringify({session_id:sid})},
 {params:{arguments:{session_id:sid}}}
];
for(const c of cases){
 if(sessionFrom(c)!==sid){console.error('Failed:',JSON.stringify(c));process.exit(1);}
}
for(const c of [null,{},[],{session_id:'../../bad'},{content:[{type:'text',text:'not-json'}]}]){
 if(sessionFrom(c)!==''){console.error('Incorrectly accepted invalid session');process.exit(2);}
}
"""
    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=10, check=False
    )
    assert completed.returncode == 0, completed.stderr
