from fastapi.testclient import TestClient

from mock.scheduler_mocks import BufferMock, MetricoolMock, PostizMock


def test_every_mock_refuses_a_wrong_key():
    assert TestClient(PostizMock().app).post("/public/v1/posts", json={}).status_code == 401
    assert TestClient(BufferMock().app).post("/", json={"query": "{ __typename }"}).status_code == 401
    assert TestClient(MetricoolMock().app).get("/admin/simpleProfiles").status_code == 401


def test_postiz_mock_checks_the_body_shape():
    m = PostizMock()
    c = TestClient(m.app)
    assert c.post("/public/v1/posts", json={"type": "bad", "posts": []}, headers={"Authorization": m.key}).status_code == 400
    ok = c.post("/public/v1/posts", json={"type": "draft", "posts": [{"integration": {"id": "a"}, "value": [{"content": "x"}]}]}, headers={"Authorization": m.key})
    assert ok.status_code == 200 and ok.json()[0]["postId"] == "pz-1"
