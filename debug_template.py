import inspect
from starlette.templating import Jinja2Templates

print("Signature:", inspect.signature(Jinja2Templates.TemplateResponse))

# Test rendering
t = Jinja2Templates(directory="templates")
try:
    resp = t.TemplateResponse("index.html", {"request": None})
    print("Call 1 OK")
except Exception as e:
    print("Call 1 failed:", type(e), e)

try:
    from starlette.requests import Request
    # mock scope
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    req = Request(scope)
    resp = t.TemplateResponse(request=req, name="index.html", context={"stats": {"total_leads": 0, "high_intent_leads": 0, "no_website_leads": 0, "contacted_leads": 0}})
    print("Call 2 OK")
except Exception as e:
    print("Call 2 failed:", type(e), e)
