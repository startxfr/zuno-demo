# Run inside the Dify api pod by `make d2 check dify`: what Dify can and cannot reach (ADR-0599).
import urllib.request as u
import urllib.error as e


def code(url):
    try:
        return str(u.urlopen(url, timeout=8).status)
    except e.HTTPError as x:
        return str(x.code)
    except Exception:
        return "000"


print("proxy=" + code("http://zuno-token-proxy:8080/healthz"))
print("ai_gateway=" + code("http://ai-gateway.zuno-ai-run.svc:8080/v1/models"))
print("mcp_gateway=" + code("http://mcp-gateway.zuno-ai-run.svc:8080/health"))
print("internet=" + code("https://huggingface.co"))
print("pypi=" + code("https://pypi.org"))
