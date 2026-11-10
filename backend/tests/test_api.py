"""API flow that needs no OpenAI key: cv analysis, generate from sketch only, modify with explicit ops."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_full_keyless_flow(client, fixture_png):
    assert client.get("/api/health").json()["ok"] is True
    up = client.post("/upload-sketch", files={"file": ("login.png", fixture_png, "image/png")}).json()
    pid, sid = up["project_id"], up["sketch_id"]
    assert up["width"] == 1000 and client.get(up["url"]).status_code == 200

    analysis = client.post("/api/analyze-sketch", json={"sketch_id": sid, "mode": "cv"}).json()
    assert len(analysis["components"]) >= 6 and client.get(analysis["overlay_url"]).status_code == 200

    v1 = client.post("/api/generate-ui", json={"project_id": pid, "sketch_id": sid, "text": "", "mode": "cv"}).json()
    assert v1["number"] == 1 and v1["kind"] == "generate" and v1["validation"]["screenshot_url"]
    assert set(v1["timings"]) >= {"upload", "analyze_sketch", "fuse", "codegen", "validate", "repair", "save", "total"}

    button = next(n["id"] for n in _walk(v1["ir"]) if n["type"] == "button")
    ops = [{"op": "style", "target": {"ref": "button", "id": button}, "changes": {"style": {"color": "blue"}}}]
    v2 = client.post("/api/modify-ui", json={"project_id": pid, "text": "make the button blue", "ops": ops}).json()
    assert v2["number"] == 2 and v2["changes"][0]["ok"] and v2["parent"] == 1

    project = client.get(f"/project/{pid}").json()
    assert [v["number"] for v in project["versions"]] == [1, 2] and project["latest"]["number"] == 2
    assert client.get(f"/api/project/{pid}").status_code == 200

    rep = client.post("/validate-ui", json={"project_id": pid, "version": 2}).json()
    assert "passed" in rep and "checks" in rep

    restored = client.post(f"/api/projects/{pid}/versions/1/restore").json()
    assert restored["kind"] == "restore" and restored["number"] == 3

    zipped = client.get(f"/api/projects/{pid}/versions/2/export.zip")
    names = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    assert any(n.endswith("src/App.jsx") for n in names) and any(n.endswith("package.json") for n in names)

    manual = client.put(f"/api/projects/{pid}/code", json={"preview": v2["preview"], "files": {}, "base_version": 2}).json()
    assert manual["kind"] == "manual_code" and manual["ir_synced"] is False

    assert client.delete(f"/api/projects/{pid}").json() == {"ok": True}


def test_streaming_generate(client, fixture_png):
    up = client.post("/api/upload-sketch", files={"file": ("s.png", fixture_png, "image/png")}).json()
    with client.stream("POST", "/api/generate-ui?stream=1",
                       json={"project_id": up["project_id"], "sketch_id": up["sketch_id"], "mode": "cv"}) as resp:
        body = "".join(resp.iter_text())
    assert '"stage": "analyze_sketch", "status": "done"' in body
    assert '"event": "result"' in body


def test_errors(client):
    assert client.get("/api/project/p_missing").status_code == 404
    bad = client.post("/api/upload-sketch", files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 415
    assert client.get("/runtime/preview.html").status_code == 200
    assert client.get("/api/samples").status_code == 200 and client.get("/api/dataset").status_code == 200


def _walk(ir):
    stack = [p["root"] for p in ir["pages"]]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("children", []))
