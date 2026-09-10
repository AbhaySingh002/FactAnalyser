import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

API_KEY = os.environ.get("API_KEY", "dev-secret-key")

async def auth_middleware(request: Request, call_next):
    # Skip auth for public endpoints
    if request.url.path in ("/health", "/"):
        return await call_next(request)
        
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # For local dev / testing fallback if no token is provided
        if os.environ.get("ENV") == "development" or os.environ.get("TESTING") == "1" or "pytest" in os.environ.get("PYTEST_CURRENT_TEST", ""):
            request.state.tenant_id = "default_tenant"
            request.state.user_id = "test_user"
            return await call_next(request)
        else:
            return JSONResponse(status_code=401, content={"error": "Missing or invalid Authorization header"})
            
    token = auth_header.split(" ")[1]
    if token != API_KEY:
        return JSONResponse(status_code=403, content={"error": "Invalid API Key"})
        
    # In a real system, we decode JWT here and set tenant context
    # request.state.tenant_id = decoded["tenant_id"]
    request.state.tenant_id = "default_tenant"
    request.state.user_id = "authenticated_user"
    
    return await call_next(request)
