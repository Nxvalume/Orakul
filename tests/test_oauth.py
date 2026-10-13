import os, importlib, hashlib, base64, re
from urllib.parse import urlencode, parse_qs, urlsplit
import pytest
import httpx

@pytest.fixture
def oauth(monkeypatch):
    monkeypatch.setenv('MINIFISH_PASSWORD','test-owner-password-long')
    monkeypatch.setenv('MINIFISH_SECRET','q'*64)
    monkeypatch.setenv('MINIFISH_MCP_TOKEN','x'*64)
    monkeypatch.setenv('MINIFISH_PUBLIC_URL','https://nxval-minifish-2026.onrender.com')
    import web_auth
    importlib.reload(web_auth)
    import oauth_server
    importlib.reload(oauth_server)
    return oauth_server

@pytest.mark.asyncio
async def test_oauth_flow(oauth):
    from starlette.applications import Starlette
    from starlette.routing import Route
    app=Starlette(routes=[Route('/oauth/register', oauth.register,methods=['POST']),
                          Route('/oauth/authorize', oauth.authorize_get,methods=['GET']),
                          Route('/oauth/authorize', oauth.authorize_post,methods=['POST']),
                          Route('/oauth/token', oauth.token,methods=['POST']),
                          Route('/.well-known/oauth-protected-resource', oauth.protected_resource),
                          Route('/.well-known/oauth-authorization-server',oauth.oauth_metadata)])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=oauth.BASE,follow_redirects=False) as c:
        md=(await c.get('/.well-known/oauth-authorization-server')).json()
        assert md['code_challenge_methods_supported']==['S256']
        assert (await c.get('/.well-known/oauth-protected-resource')).json()['authorization_servers']==[oauth.BASE]
        assert (await c.post('/oauth/register',json={'redirect_uris':['https://evil.example/callback']})).status_code==400
        reg=await c.post('/oauth/register',json={'redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect']})
        assert reg.status_code==201,reg.text
        client_id=reg.json()['client_id']
        verifier='r'*60
        challenge=oauth.encode_bytes(hashlib.sha256(verifier.encode()).digest())
        args={'client_id':client_id,'redirect_uri':'https://chatgpt.com/connector_platform_oauth_redirect',
              'response_type':'code','code_challenge_method':'S256','code_challenge':challenge,
              'state':'a'*32,'scope':'browser:read browser:act','resource':oauth.BASE}
        assert (await c.get('/oauth/authorize',params={**args,'code_challenge':'bad'})).status_code==400
        form=await c.get('/oauth/authorize',params=args)
        assert form.status_code==200
        ticket=re.search(r'name="ticket" value="([^"]+)',form.text).group(1)
        denied=await c.post('/oauth/authorize',data={'ticket':ticket,'password':'wrong'})
        assert denied.status_code==401
        ok=await c.post('/oauth/authorize',data={'ticket':ticket,'password':'test-owner-password-long'})
        assert ok.status_code==303,ok.text
        loc=urlsplit(ok.headers['location'])
        assert loc.netloc=='chatgpt.com'
        vals={k:v[0] for k,v in parse_qs(loc.query).items()}
        assert vals['state']==args['state'] and vals['iss']==oauth.BASE
        body={'grant_type':'authorization_code','code':vals['code'],'redirect_uri':args['redirect_uri'],
              'client_id':client_id,'code_verifier':verifier,'resource':oauth.BASE}
        wrong=await c.post('/oauth/token',data={**body,'code_verifier':'invalid'*9})
        assert wrong.status_code==400
        replay=await c.post('/oauth/token',data=body)
        assert replay.status_code==400
        form2=await c.get('/oauth/authorize',params=args)
        ticket2=re.search(r'name="ticket" value="([^"]+)',form2.text).group(1)
        ok2=await c.post('/oauth/authorize',data={'ticket':ticket2,'password':'test-owner-password-long'})
        vals2={k:v[0] for k,v in parse_qs(urlsplit(ok2.headers['location']).query).items()}
        body['code']=vals2['code']
        token=await c.post('/oauth/token',data=body)
        assert token.status_code==200,token.text
        data=token.json()
        assert oauth.authorized_access(data['access_token'])
        assert not oauth.authorized_access(data['access_token']+'spoof')
        assert (await c.post('/oauth/token',data=body)).status_code==400
        refreshed=await c.post('/oauth/token',data={'grant_type':'refresh_token','client_id':client_id,'refresh_token':data['refresh_token']})
        assert refreshed.status_code==200
        assert oauth.authorized_access(refreshed.json()['access_token'])


def test_redirect_protection_and_expired_tokens(oauth):
    for path in ['https://chatgpt.com.evil.com/connector_platform_oauth_redirect',
                 'http://chatgpt.com/connector_platform_oauth_redirect',
                 'https://chatgpt.com/cb',
                 'https://chatgpt.com/connector_platform_oauth_redirect#bad']:
        assert not oauth.client_redirect_allowed(path)
    exp=oauth.sign({'kind':'access','aud':oauth.BASE,'scope':'browser:read browser:act','iat':0,'exp':1})
    assert not oauth.authorized_access(exp)
    scope=oauth.sign({'kind':'access','aud':oauth.BASE,'scope':'browser:read','iat':int(__import__('time').time()),'exp':int(__import__('time').time())+30})
    assert not oauth.authorized_access(scope)
