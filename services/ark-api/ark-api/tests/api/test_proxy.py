"""Tests for proxy endpoints."""
import os
import unittest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

os.environ["AUTH_MODE"] = "open"


class TestProxyMCP(unittest.TestCase):
    """Test cases for MCP proxy endpoints."""
    
    def setUp(self):
        """Set up test client."""
        from ark_api.main import app
        self.client = TestClient(app)
    
    @patch('ark_api.api.v1.proxy.httpx.AsyncClient')
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_mcp_success(self, mock_with_ark_client, mock_httpx_client):
        """Test successful MCP proxy request."""
        mock_client = AsyncMock()
        mock_mcp_server = Mock()
        mock_mcp_server.to_dict.return_value = {
            "metadata": {"name": "test-mcp"},
            "spec": {
                "headers": [
                    {"name": "Authorization", "value": {"value": "Bearer token123"}}
                ]
            },
            "status": {"resolvedAddress": "http://mcp-server:8080"}
        }
        mock_client.mcpservers.a_get = AsyncMock(return_value=mock_mcp_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.content = b'{"result": "success"}'
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_client_instance = AsyncMock()
        mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
        
        response = self.client.get("/proxy/mcp/test-mcp")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"result": "success"})
        mock_client.mcpservers.a_get.assert_called_once_with("test-mcp")
        mock_http_client_instance.request.assert_called_once()
        call_kwargs = mock_http_client_instance.request.call_args[1]
        self.assertEqual(call_kwargs["method"], "GET")
        self.assertIn("http://mcp-server:8080", call_kwargs["url"])
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer token123")
    
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_mcp_with_path(self, mock_with_ark_client):
        """Test MCP proxy with path suffix."""
        mock_client = AsyncMock()
        mock_mcp_server = Mock()
        mock_mcp_server.to_dict.return_value = {
            "metadata": {"name": "test-mcp"},
            "spec": {"headers": []},
            "status": {"resolvedAddress": "http://mcp-server:8080"}
        }
        mock_client.mcpservers.a_get = AsyncMock(return_value=mock_mcp_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        with patch('ark_api.api.v1.proxy.httpx.AsyncClient') as mock_httpx_client:
            mock_http_response = Mock()
            mock_http_response.status_code = 200
            mock_http_response.content = b'{"tools": []}'
            mock_http_response.headers = {"content-type": "application/json"}
            mock_http_client_instance = AsyncMock()
            mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
            mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
            
            response = self.client.get("/proxy/mcp/test-mcp/sse")
            
            self.assertEqual(response.status_code, 200)
            call_kwargs = mock_http_client_instance.request.call_args[1]
            self.assertIn("/sse", call_kwargs["url"])
    
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_mcp_not_found(self, mock_with_ark_client):
        """Test MCP proxy when server not found."""
        mock_client = AsyncMock()
        mock_client.mcpservers.a_get = AsyncMock(side_effect=Exception("Not found"))
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        response = self.client.get("/proxy/mcp/nonexistent")
        
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())
    
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_mcp_no_resolved_address(self, mock_with_ark_client):
        """Test MCP proxy when server has no resolved address."""
        mock_client = AsyncMock()
        mock_mcp_server = Mock()
        mock_mcp_server.to_dict.return_value = {
            "metadata": {"name": "test-mcp"},
            "spec": {"headers": []},
            "status": {}
        }
        mock_client.mcpservers.a_get = AsyncMock(return_value=mock_mcp_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        response = self.client.get("/proxy/mcp/test-mcp")
        
        self.assertEqual(response.status_code, 503)
        self.assertIn("resolved address", response.json()["detail"].lower())
    
    @patch('ark_api.api.v1.proxy.httpx.AsyncClient')
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_mcp_post_request(self, mock_with_ark_client, mock_httpx_client):
        """Test MCP proxy with POST request."""
        mock_client = AsyncMock()
        mock_mcp_server = Mock()
        mock_mcp_server.to_dict.return_value = {
            "metadata": {"name": "test-mcp"},
            "spec": {"headers": []},
            "status": {"resolvedAddress": "http://mcp-server:8080"}
        }
        mock_client.mcpservers.a_get = AsyncMock(return_value=mock_mcp_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        mock_http_response = Mock()
        mock_http_response.status_code = 201
        mock_http_response.content = b'{"id": "123"}'
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_client_instance = AsyncMock()
        mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
        
        response = self.client.post(
            "/proxy/mcp/test-mcp/tools",
            json={"name": "test-tool"}
        )
        
        self.assertEqual(response.status_code, 201)
        call_kwargs = mock_http_client_instance.request.call_args[1]
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertIsNotNone(call_kwargs["content"])


class TestProxyA2A(unittest.TestCase):
    """Test cases for A2A proxy endpoints."""
    
    def setUp(self):
        """Set up test client."""
        from ark_api.main import app
        self.client = TestClient(app)
    
    @patch('ark_api.api.v1.proxy.httpx.AsyncClient')
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_a2a_success(self, mock_with_ark_client, mock_httpx_client):
        """Test successful A2A proxy request."""
        mock_client = AsyncMock()
        mock_a2a_server = Mock()
        mock_a2a_server.to_dict.return_value = {
            "metadata": {"name": "test-a2a"},
            "spec": {
                "headers": [
                    {"name": "X-API-Key", "value": {"value": "key123"}}
                ]
            },
            "status": {"lastResolvedAddress": "http://a2a-server:8080"}
        }
        mock_client.a2aservers.a_get = AsyncMock(return_value=mock_a2a_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.content = b'{"agent": "test-agent"}'
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_client_instance = AsyncMock()
        mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
        
        response = self.client.get("/proxy/a2a/test-a2a")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"agent": "test-agent"})
        mock_client.a2aservers.a_get.assert_called_once_with("test-a2a")
        call_kwargs = mock_http_client_instance.request.call_args[1]
        self.assertIn("X-API-Key", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["X-API-Key"], "key123")
    
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_a2a_not_found(self, mock_with_ark_client):
        """Test A2A proxy when server not found."""
        mock_client = AsyncMock()
        mock_client.a2aservers.a_get = AsyncMock(side_effect=Exception("Not found"))
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        response = self.client.get("/proxy/a2a/nonexistent")
        
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())
    
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_a2a_no_resolved_address(self, mock_with_ark_client):
        """Test A2A proxy when server has no resolved address."""
        mock_client = AsyncMock()
        mock_a2a_server = Mock()
        mock_a2a_server.to_dict.return_value = {
            "metadata": {"name": "test-a2a"},
            "spec": {"headers": []},
            "status": {}
        }
        mock_client.a2aservers.a_get = AsyncMock(return_value=mock_a2a_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        response = self.client.get("/proxy/a2a/test-a2a")
        
        self.assertEqual(response.status_code, 503)
        self.assertIn("resolved address", response.json()["detail"].lower())
    
    @patch('ark_api.api.v1.proxy.httpx.AsyncClient')
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_a2a_with_query_params(self, mock_with_ark_client, mock_httpx_client):
        """Test A2A proxy with query parameters."""
        mock_client = AsyncMock()
        mock_a2a_server = Mock()
        mock_a2a_server.to_dict.return_value = {
            "metadata": {"name": "test-a2a"},
            "spec": {"headers": []},
            "status": {"lastResolvedAddress": "http://a2a-server:8080"}
        }
        mock_client.a2aservers.a_get = AsyncMock(return_value=mock_a2a_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.content = b'[]'
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_client_instance = AsyncMock()
        mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
        
        response = self.client.get("/proxy/a2a/test-a2a/agents?limit=10")
        
        self.assertEqual(response.status_code, 200)
        call_kwargs = mock_http_client_instance.request.call_args[1]
        self.assertIn("limit=10", call_kwargs["url"])


class TestProxyHeaders(unittest.TestCase):
    """Test cases for header resolution in proxy."""
    
    def setUp(self):
        """Set up test client."""
        from ark_api.main import app
        self.client = TestClient(app)
    
    @patch('ark_api.api.v1.proxy.httpx.AsyncClient')
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_headers_from_spec(self, mock_with_ark_client, mock_httpx_client):
        """Test that headers from server spec are included."""
        mock_client = AsyncMock()
        mock_mcp_server = Mock()
        mock_mcp_server.to_dict.return_value = {
            "metadata": {"name": "test-mcp"},
            "spec": {
                "headers": [
                    {"name": "Authorization", "value": {"value": "Bearer secret"}},
                    {"name": "X-Custom-Header", "value": {"value": "custom-value"}}
                ]
            },
            "status": {"resolvedAddress": "http://mcp-server:8080"}
        }
        mock_client.mcpservers.a_get = AsyncMock(return_value=mock_mcp_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.content = b'{}'
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_client_instance = AsyncMock()
        mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
        
        response = self.client.get("/proxy/mcp/test-mcp", headers={"X-Request-ID": "123"})
        
        self.assertEqual(response.status_code, 200)
        call_kwargs = mock_http_client_instance.request.call_args[1]
        headers = call_kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["X-Custom-Header"], "custom-value")
        self.assertEqual(headers["X-Request-ID"], "123")
    
    @patch('ark_api.api.v1.proxy.httpx.AsyncClient')
    @patch('ark_api.api.v1.proxy.with_ark_client')
    def test_proxy_request_headers_excluded(self, mock_with_ark_client, mock_httpx_client):
        """Test that certain request headers are excluded from proxy."""
        mock_client = AsyncMock()
        mock_mcp_server = Mock()
        mock_mcp_server.to_dict.return_value = {
            "metadata": {"name": "test-mcp"},
            "spec": {"headers": []},
            "status": {"resolvedAddress": "http://mcp-server:8080"}
        }
        mock_client.mcpservers.a_get = AsyncMock(return_value=mock_mcp_server)
        mock_with_ark_client.return_value.__aenter__.return_value = mock_client
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.content = b'{}'
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_client_instance = AsyncMock()
        mock_http_client_instance.request = AsyncMock(return_value=mock_http_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_http_client_instance
        
        response = self.client.get("/proxy/mcp/test-mcp", headers={"Host": "original-host"})
        
        self.assertEqual(response.status_code, 200)
        call_kwargs = mock_http_client_instance.request.call_args[1]
        headers = call_kwargs["headers"]
        self.assertNotIn("Host", headers)

