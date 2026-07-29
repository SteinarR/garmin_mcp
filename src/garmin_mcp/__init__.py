"""
Modular MCP Server for Garmin Connect Data
"""

import json
import os

import requests
from mcp.server.fastmcp import FastMCP

from garth.exc import GarthHTTPError
from garminconnect import Garmin, GarminConnectAuthenticationError


def _to_json_str(data):
    """Convert data to JSON string if it's not already a string"""
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, indent=2, default=str)
    except (TypeError, ValueError):
        return str(data)

# Import all modules
from garmin_mcp import activity_management
from garmin_mcp import health_wellness
from garmin_mcp import user_profile
from garmin_mcp import devices
from garmin_mcp import gear_management
from garmin_mcp import weight_management
from garmin_mcp import challenges
from garmin_mcp import training
from garmin_mcp import workouts
from garmin_mcp import data_management
from garmin_mcp import womens_health
from garmin_mcp import recommendations
from garmin_mcp.cached_client import build_cached_client

def get_mfa() -> str:
    """Get MFA code non-interactively for container/Kubernetes environments.

    Sources (checked in order):
    - GARMIN_MFA_CODE env var
    - GARMIN_MFA_CODE_FILE pointing to a file containing the code
    - Poll for up to GARMIN_MFA_WAIT_SECONDS for either of the above to appear
    """
    print("\nGarmin Connect MFA required. Awaiting code via env or file...")

    mfa_code = os.environ.get("GARMIN_MFA_CODE")
    if mfa_code:
        return mfa_code.strip()

    mfa_file = os.environ.get("GARMIN_MFA_CODE_FILE")
    if mfa_file and os.path.exists(os.path.expanduser(mfa_file)):
        with open(os.path.expanduser(mfa_file), "r") as f:
            return f.read().strip()

    # Optional polling window to allow sidecar/secret updates
    wait_seconds = int(os.environ.get("GARMIN_MFA_WAIT_SECONDS", "0") or 0)
    if wait_seconds > 0:
        import time

        end_time = time.time() + wait_seconds
        while time.time() < end_time:
            mfa_code = os.environ.get("GARMIN_MFA_CODE")
            if mfa_code:
                return mfa_code.strip()

            mfa_file = os.environ.get("GARMIN_MFA_CODE_FILE")
            if mfa_file and os.path.exists(os.path.expanduser(mfa_file)):
                with open(os.path.expanduser(mfa_file), "r") as f:
                    return f.read().strip()

            time.sleep(1)

    raise RuntimeError(
        "MFA code required but not provided. Set GARMIN_MFA_CODE or GARMIN_MFA_CODE_FILE "
        "(optional: GARMIN_MFA_WAIT_SECONDS to poll)."
    )

# Get credentials from environment
email = os.environ.get("GARMIN_EMAIL")
password = os.environ.get("GARMIN_PASSWORD")
tokenstore = os.getenv("GARMINTOKENS") or "~/.garminconnect"
tokenstore_base64 = os.getenv("GARMINTOKENS_BASE64") or "~/.garminconnect_base64"


def init_api(email, password):
    """Initialize Garmin API with your credentials."""

    try:
        # Using Oauth1 and OAuth2 token files from directory
        print(
            f"Trying to login to Garmin Connect using token data from directory '{tokenstore}'...\n"
        )

        # Using Oauth1 and Oauth2 tokens from base64 encoded string
        # print(
        #     f"Trying to login to Garmin Connect using token data from file '{tokenstore_base64}'...\n"
        # )
        # dir_path = os.path.expanduser(tokenstore_base64)
        # with open(dir_path, "r") as token_file:
        #     tokenstore = token_file.read()

        garmin = Garmin()
        garmin.login(tokenstore)

    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
        # Session is expired. You'll need to log in again
        print(
            "Login tokens not present, login with your Garmin Connect credentials to generate them.\n"
            f"They will be stored in '{tokenstore}' for future use.\n"
        )
        try:
            garmin = Garmin(
                email=email, password=password, is_cn=False, prompt_mfa=get_mfa
            )
            garmin.login()
            # Save Oauth1 and Oauth2 token files to directory for next login
            garmin.garth.dump(tokenstore)
            print(
                f"Oauth tokens stored in '{tokenstore}' directory for future use. (first method)\n"
            )
            # Encode Oauth1 and Oauth2 tokens to base64 string and safe to file for next login (alternative way)
            token_base64 = garmin.garth.dumps()
            dir_path = os.path.expanduser(tokenstore_base64)
            with open(dir_path, "w") as token_file:
                token_file.write(token_base64)
            print(
                f"Oauth tokens encoded as base64 string and saved to '{dir_path}' file for future use. (second method)\n"
            )
        except (
            FileNotFoundError,
            GarthHTTPError,
            GarminConnectAuthenticationError,
            requests.exceptions.HTTPError,
        ) as err:
            print(err)
            return None

    return garmin


def main():
    """Initialize the MCP server and register all tools"""

    # Initialize Garmin client
    garmin_client = init_api(email, password)
    if not garmin_client:
        print("Failed to initialize Garmin Connect client. Exiting.")
        return

    print("Garmin Connect client initialized successfully.")

    # Optionally wrap the client so settled reads are served from the
    # garmin-ingestor output instead of the Garmin API. No-op unless
    # GARMIN_CACHE_ENABLED is set.
    garmin_client = build_cached_client(garmin_client)

    # Configure all modules with the Garmin client
    activity_management.configure(garmin_client)
    health_wellness.configure(garmin_client)
    user_profile.configure(garmin_client)
    devices.configure(garmin_client)
    gear_management.configure(garmin_client)
    weight_management.configure(garmin_client)
    challenges.configure(garmin_client)
    training.configure(garmin_client)
    workouts.configure(garmin_client)
    data_management.configure(garmin_client)
    womens_health.configure(garmin_client)
    recommendations.configure(garmin_client)

    # Create the MCP app
    app = FastMCP("Garmin Connect v1.0")

    # Register tools from all modules
    app = activity_management.register_tools(app)
    app = health_wellness.register_tools(app)
    app = user_profile.register_tools(app)
    app = devices.register_tools(app)
    app = gear_management.register_tools(app)
    app = weight_management.register_tools(app)
    app = challenges.register_tools(app)
    app = training.register_tools(app)
    app = workouts.register_tools(app)
    app = data_management.register_tools(app)
    app = womens_health.register_tools(app)
    app = recommendations.register_tools(app)

    # Add simple HTTP health and root routes if the underlying ASGI app exposes FastAPI-style router
    try:
        asgi = getattr(app, "app", None) or getattr(app, "asgi", None) or getattr(app, "asgi_app", None) or getattr(app, "_app", None)
        if asgi is not None and hasattr(asgi, "add_api_route"):
            from typing import Any
            def _ok() -> Any:
                return {"status": "ok", "service": "garmin-mcp"}
            # Health endpoints commonly used by k8s/istio
            asgi.add_api_route("/healthz", _ok, methods=["GET"])  # type: ignore[attr-defined]
            asgi.add_api_route("/readyz", _ok, methods=["GET"])  # type: ignore[attr-defined]
            # Friendly root so GET / doesn't 404
            asgi.add_api_route("/", _ok, methods=["GET"])  # type: ignore[attr-defined]
    except Exception:
        pass

    # Add activity listing tool directly to the app
    @app.tool()
    async def list_activities(limit: int = 5) -> str:
        """List recent Garmin activities"""
        try:
            activities = garmin_client.get_activities(0, limit)

            if not activities:
                return "No activities found."

            return _to_json_str(activities)
        except Exception as e:
            return f"Error retrieving activities: {str(e)}"

    # Run the MCP server (Streamable HTTP by default for Kubernetes)
    transport = os.environ.get("GARMIN_MCP_TRANSPORT", "http")
    host = os.environ.get("GARMIN_MCP_HOST", "0.0.0.0")
    port_str = os.environ.get("GARMIN_MCP_PORT", "8000")
    path = os.environ.get("GARMIN_MCP_PATH", "/")
    try:
        port = int(port_str)
    except ValueError:
        port = 8000

    if transport == "stdio":
        app.run()
    else:
        print(f"Starting MCP with transport={transport}, host={host}, port={port}, path={path}")
        # Provide simple health endpoints by wrapping the ASGI app when possible
        class _HealthWrapper:
            def __init__(self, inner):
                self.inner = inner

            async def __call__(self, scope, receive, send):
                if scope.get("type") == "http" and scope.get("method") == "GET":
                    path_value = scope.get("path", "")
                    if path_value in ("/", "/healthz", "/readyz"):
                        body = b'{"status":"ok","service":"garmin-mcp"}'
                        await send({
                            "type": "http.response.start",
                            "status": 200,
                            "headers": [(b"content-type", b"application/json")],
                        })
                        await send({"type": "http.response.body", "body": body})
                        return
                return await self.inner(scope, receive, send)

        # Aggressively monkey-patch uvicorn at multiple levels to force 0.0.0.0 binding
        if host == "0.0.0.0":
            try:
                import uvicorn  # type: ignore
                import uvicorn.config  # type: ignore
                import uvicorn.server  # type: ignore
                
                # Patch uvicorn.run
                original_run = uvicorn.run
                def patched_run(app, *args, **kwargs):
                    if "host" not in kwargs or kwargs.get("host") == "127.0.0.1":
                        kwargs["host"] = "0.0.0.0"
                    if "port" not in kwargs and port:
                        kwargs["port"] = port
                    return original_run(app, *args, **kwargs)
                uvicorn.run = patched_run
                
                # Patch Config.__init__ to force host
                original_config_init = uvicorn.config.Config.__init__
                def patched_config_init(self, *args, **kwargs):
                    if "host" not in kwargs or kwargs.get("host") == "127.0.0.1" or kwargs.get("host") is None:
                        kwargs["host"] = "0.0.0.0"
                    if "port" not in kwargs and port:
                        kwargs["port"] = port
                    return original_config_init(self, *args, **kwargs)
                uvicorn.config.Config.__init__ = patched_config_init
                
                # Patch Server.__init__ to force host
                original_server_init = uvicorn.server.Server.__init__
                def patched_server_init(self, config, *args, **kwargs):
                    if hasattr(config, 'host') and (config.host == "127.0.0.1" or config.host is None):
                        config.host = "0.0.0.0"
                    if hasattr(config, 'port') and not config.port and port:
                        config.port = port
                    return original_server_init(self, config, *args, **kwargs)
                uvicorn.server.Server.__init__ = patched_server_init
                
                print("Patched uvicorn at multiple levels to force 0.0.0.0 binding")
            except Exception as e:
                print(f"Warning: Could not patch uvicorn: {e}")

        # Try to locate the underlying ASGI app and run it directly (wrapped) so health endpoints work
        try:
            import uvicorn  # type: ignore
            underlying = getattr(app, "app", None) or getattr(app, "asgi", None) or getattr(app, "asgi_app", None) or getattr(app, "_app", None)
            if underlying is None:
                for factory_name in ("build_asgi", "create_asgi", "make_asgi_app"):
                    factory = getattr(app, factory_name, None)
                    if callable(factory):
                        underlying = factory()
                        break
            if underlying is not None:
                wrapped = _HealthWrapper(underlying)
                uvicorn.run(wrapped, host=host, port=port)
                return
        except Exception:
            pass
        # Try to run with explicit parameters first
        try:
            app.run(transport=transport, host=host, port=port, path=path)
            return
        except TypeError:
            pass
        try:
            app.run(transport=transport, hostname=host, port=port, path=path)
            return
        except TypeError:
            pass
        try:
            app.run(transport=transport, address=host, port=port, path=path)
            return
        except TypeError:
            pass
        # Final fallback - the monkey-patch should catch this
        app.run(transport=transport)


if __name__ == "__main__":
    main()
