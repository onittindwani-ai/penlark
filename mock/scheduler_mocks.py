"""Mock Postiz, Buffer and Metricool servers written from public docs. Postiz and Buffer shapes were read on 2026-11-23, Metricool from memory. Nothing here is the real service."""

from __future__ import annotations

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse


class PostizMock:
    def __init__(self, key="pz-mock-key"):
        self.key, self.posts, self.app = key, [], FastAPI()

        @self.app.get("/public/v1/integrations")
        def integrations(authorization: str | None = Header(default=None)):
            return JSONResponse({"error": "unauthorized"}, 401) if authorization != self.key else [{"id": "ch-1", "name": "Sample LinkedIn", "identifier": "linkedin"}]

        @self.app.post("/public/v1/posts")
        async def create(request: Request, authorization: str | None = Header(default=None)):
            if authorization != self.key:
                return JSONResponse({"error": "unauthorized"}, 401)
            body = await request.json()
            if body.get("type") not in {"draft", "schedule", "now"} or not body.get("posts"):
                return JSONResponse({"error": "bad body"}, 400)
            self.posts.append(body)
            return [{"postId": f"pz-{len(self.posts)}", "integration": body["posts"][0]["integration"]["id"]}]


class BufferMock:
    def __init__(self, token="bf-mock-token"):
        self.token, self.posts, self.app = token, [], FastAPI()

        @self.app.post("/")
        async def gql(request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"errors": [{"message": "unauthorized"}]}, 401)
            body = await request.json()
            if "createPost" not in body.get("query", ""):
                return {"data": {"__typename": "Query"}}
            inp = body["variables"]["input"]
            if not inp.get("channelId"):
                return {"data": {"createPost": {"message": "channelId is required"}}}
            self.posts.append(inp)
            return {"data": {"createPost": {"post": {"id": f"bf-{len(self.posts)}", "text": inp["text"]}}}}


class MetricoolMock:
    def __init__(self, token="mc-mock-token"):
        self.token, self.posts, self.app = token, [], FastAPI()

        @self.app.get("/admin/simpleProfiles")
        def profiles(x_mc_auth: str | None = Header(default=None)):
            return JSONResponse({"error": "unauthorized"}, 401) if x_mc_auth != self.token else []

        @self.app.post("/v2/scheduler/posts")
        async def create(request: Request, x_mc_auth: str | None = Header(default=None)):
            if x_mc_auth != self.token:
                return JSONResponse({"error": "unauthorized"}, 401)
            self.posts.append(await request.json())
            return {"data": {"id": f"mc-{len(self.posts)}"}}
