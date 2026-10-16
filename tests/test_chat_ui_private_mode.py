"""Android widget must not operate model-visible controls in owner private mode."""
import re
import shutil
import subprocess

import pytest

from chat_ui import CHAT_HTML


def test_protected_mode_hides_public_controls_and_restores_only_after_release():
    assert 'id="publicControls"' in CHAT_HTML
    assert "function publicView(enabled)" in CHAT_HTML
    assert "publicView(false);" in CHAT_HTML
    assert "publicView(true);" in CHAT_HTML
    assert CHAT_HTML.count("if(!session||busy||secureToken||privateLocked)return;") == 2
    assert "if(session&&!busy&&!secureToken&&!privateLocked" in CHAT_HTML
    assert "if(ownerDenied(e))lockPrivateView(" in CHAT_HTML
    assert "if(next && next!==session && !secureToken && !privateLocked)" in CHAT_HTML


def test_private_frame_does_not_embed_owner_token_in_image_url_or_mcp():
    assert "await drawFrame($('secureShot'),blob)" in CHAT_HTML
    assert "await drawFrame($('shot'),new Blob(" in CHAT_HTML
    assert "createImageBitmap(blob)" in CHAT_HTML
    assert "ctx.drawImage(bitmap,0,0)" in CHAT_HTML
    assert "URL.createObjectURL(blob)" not in CHAT_HTML
    assert "reader.readAsDataURL(blob)" not in CHAT_HTML
    assert '<canvas id="shot"' in CHAT_HTML
    assert '<canvas id="secureShot"' in CHAT_HTML
    assert "secureAction('telegram_open',{})" in CHAT_HTML
    assert "secureRequest('frame',null,'GET')" in CHAT_HTML
    assert "headers['X-MiniFish-Owner']=secureToken" in CHAT_HTML
    assert "bridge('tools/call',{name,arguments:args})" in CHAT_HTML
    assert "secureAction('scroll',{pixels:-460})" in CHAT_HTML
    assert "secureAction('scroll',{pixels:460})" in CHAT_HTML
    assert "Защищённый доступ истёк" in CHAT_HTML


def test_failed_profile_checkpoint_never_reenables_model_ui():
    assert "if(result.private_mode){" in CHAT_HTML
    block = CHAT_HTML.split("if(result.private_mode){", 1)[1].split("if(securePoll)", 1)[0]
    assert "return;" in block
    assert "result.save_error" in block


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js unavailable")
def test_embedded_browser_javascript_parses_without_syntax_errors():
    match = re.search(r"(?s)<script>\s*(.*?)\s*</script>", CHAT_HTML)
    assert match is not None
    result = subprocess.run(["node", "--check"], input=match.group(1),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
