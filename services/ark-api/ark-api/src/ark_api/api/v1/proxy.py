"""Proxy endpoints for MCP and A2A servers."""
import logging
from typing import Optional, Dict, Any
import httpx
from fastapi import APIRouter, Request, Response, Query, HTTPException
from ark_sdk.client import with_ark_client

from .exceptions import handle_k8s_errors

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/proxy", tags=["proxy"])

MCP_VERSION = "v1alpha1"
A2A_VERSION = "v1prealpha1"


def resolve_headers_from_spec(headers: list, namespace: str) -> Dict[str, str]:
    """
    Resolve headers from spec to a dictionary.
    Currently only handles direct values, not ValueSource references.
    
    Args:
        headers: List of header specs from CRD
        namespace: Namespace for resolving references (not used for direct values)
        
    Returns:
        Dictionary of header name -> value
    """
    resolved = {}
    for header in headers:
        name = header.get("name")
        value_spec = header.get("value", {})
        
        if name and value_spec:
            if "value" in value_spec:
                resolved[name] = value_spec["value"]
            else:
                logger.warning(
                    f"Header {name} uses ValueSource reference, which is not yet supported in proxy. "
                    "Skipping this header."
                )
    
    return resolved


async def get_mcp_server_address(
    mcp_server_name: str,
    namespace: Optional[str]
) -> tuple[str, Dict[str, str]]:
    """
    Get the resolved address and headers for an MCP server.
    
    Args:
        mcp_server_name: Name of the MCP server
        namespace: Namespace (defaults to current context)
        
    Returns:
        Tuple of (resolved_address, headers_dict)
        
    Raises:
        HTTPException: If server not found or not ready
    """
    async with with_ark_client(namespace, MCP_VERSION) as ark_client:
        try:
            mcp_server = await ark_client.mcpservers.a_get(mcp_server_name)
            mcp_dict = mcp_server.to_dict()
        except Exception as e:
            logger.error(f"Failed to get MCP server {mcp_server_name}: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"MCP server '{mcp_server_name}' not found"
            )
        
        status = mcp_dict.get("status", {})
        resolved_address = status.get("resolvedAddress")
        
        if not resolved_address:
            raise HTTPException(
                status_code=503,
                detail=f"MCP server '{mcp_server_name}' has no resolved address. It may not be ready yet."
            )
        
        spec = mcp_dict.get("spec", {})
        headers = spec.get("headers", [])
        resolved_headers = resolve_headers_from_spec(headers, namespace or "default")
        
        return resolved_address.rstrip("/"), resolved_headers


async def get_a2a_server_address(
    a2a_server_name: str,
    namespace: Optional[str]
) -> tuple[str, Dict[str, str]]:
    """
    Get the resolved address and headers for an A2A server.
    
    Args:
        a2a_server_name: Name of the A2A server
        namespace: Namespace (defaults to current context)
        
    Returns:
        Tuple of (resolved_address, headers_dict)
        
    Raises:
        HTTPException: If server not found or not ready
    """
    async with with_ark_client(namespace, A2A_VERSION) as ark_client:
        try:
            a2a_server = await ark_client.a2aservers.a_get(a2a_server_name)
            a2a_dict = a2a_server.to_dict()
        except Exception as e:
            logger.error(f"Failed to get A2A server {a2a_server_name}: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"A2A server '{a2a_server_name}' not found"
            )
        
        status = a2a_dict.get("status", {})
        resolved_address = status.get("lastResolvedAddress")
        
        if not resolved_address:
            raise HTTPException(
                status_code=503,
                detail=f"A2A server '{a2a_server_name}' has no resolved address. It may not be ready yet."
            )
        
        spec = a2a_dict.get("spec", {})
        headers = spec.get("headers", [])
        resolved_headers = resolve_headers_from_spec(headers, namespace or "default")
        
        return resolved_address.rstrip("/"), resolved_headers


async def proxy_request(
    target_url: str,
    request: Request,
    additional_headers: Dict[str, str],
    path_suffix: str = ""
) -> Response:
    """
    Proxy an HTTP request to a target URL.
    
    Args:
        target_url: Base URL of the target server
        request: Original FastAPI request
        additional_headers: Additional headers to include (from server spec)
        path_suffix: Path to append to target_url (after removing proxy prefix)
        
    Returns:
        Response from the target server
    """
    method = request.method
    query_params = dict(request.query_params)
    
    url = f"{target_url}{path_suffix}"
    if query_params:
        from urllib.parse import urlencode
        url += f"?{urlencode(query_params)}"
    
    headers = {}
    for name, value in request.headers.items():
        lower_name = name.lower()
        if lower_name not in ("host", "content-length", "connection", "transfer-encoding"):
            headers[name] = value
    
    for name, value in additional_headers.items():
        headers[name] = value
    
    body = None
    if method in ("POST", "PUT", "PATCH"):
        body = await request.body()
    
    timeout = httpx.Timeout(30.0, read=None)
    
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
            )
            
            response_headers = dict(response.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("transfer-encoding", None)
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get("content-type")
            )
    except httpx.RequestError as e:
        logger.error(f"Proxy request failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to proxy request to {target_url}: {str(e)}"
        )


@router.api_route("/mcp/{mcp_server_name}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
@router.api_route("/mcp/{mcp_server_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
@handle_k8s_errors(operation="proxy", resource_type="mcp server")
async def proxy_mcp(
    mcp_server_name: str,
    request: Request,
    path: Optional[str] = None,
    namespace: Optional[str] = Query(None, description="Namespace for this request (defaults to current context)")
) -> Response:
    """
    Proxy requests to an MCP server.
    
    This endpoint forwards all HTTP requests to the resolved address of the specified MCP server.
    Useful for tools like MCP inspector that need direct access to MCP servers.
    
    Args:
        mcp_server_name: Name of the MCP server to proxy to
        request: The HTTP request to proxy
        path: Optional path suffix to append to the target URL
        namespace: Namespace containing the MCP server
        
    Returns:
        Response from the MCP server
    """
    target_url, headers = await get_mcp_server_address(mcp_server_name, namespace)
    
    path_suffix = ""
    if path:
        path_suffix = f"/{path}" if not path.startswith("/") else path
    
    return await proxy_request(target_url, request, headers, path_suffix)


@router.api_route("/a2a/{a2a_server_name}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
@router.api_route("/a2a/{a2a_server_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
@handle_k8s_errors(operation="proxy", resource_type="a2a server")
async def proxy_a2a(
    a2a_server_name: str,
    request: Request,
    path: Optional[str] = None,
    namespace: Optional[str] = Query(None, description="Namespace for this request (defaults to current context)")
) -> Response:
    """
    Proxy requests to an A2A server.
    
    This endpoint forwards all HTTP requests to the resolved address of the specified A2A server.
    Useful for tools like A2A inspector that need direct access to A2A servers.
    
    Args:
        a2a_server_name: Name of the A2A server to proxy to
        request: The HTTP request to proxy
        path: Optional path suffix to append to the target URL
        namespace: Namespace containing the A2A server
        
    Returns:
        Response from the A2A server
    """
    target_url, headers = await get_a2a_server_address(a2a_server_name, namespace)
    
    path_suffix = ""
    if path:
        path_suffix = f"/{path}" if not path.startswith("/") else path
    
    return await proxy_request(target_url, request, headers, path_suffix)

