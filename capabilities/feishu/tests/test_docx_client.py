"""离线测试：FeishuDocxClient（注入 fake HTTP，不触网）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[3]
for _p in (str(_PRJ),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from capabilities.feishu.auth import FeishuAPIError, _TOKEN_CACHE  # noqa: E402
from capabilities.feishu.docx import FeishuDocxClient, to_markdown  # noqa: E402


class _Resp:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body
        self.content = b"x"
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._body


class _HTTP:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None, **kw):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers, **kw})
        for key, resp in self.routes:
            if key in url:
                return resp
        raise AssertionError(f"no route for {method} {url}")


@pytest.fixture(autouse=True)
def _reset_token_cache():
    _TOKEN_CACHE["token"] = None
    _TOKEN_CACHE["expire_at"] = 0.0
    yield
    _TOKEN_CACHE["token"] = None
    _TOKEN_CACHE["expire_at"] = 0.0


def _client(routes, **kw):
    return FeishuDocxClient(
        app_id="cli_test",
        app_secret="secret",
        folder_token="fld_test",
        host="r4i0myjr3j.feishu.cn",
        base="https://open.feishu.cn/open-apis",
        http=_HTTP(routes),
        **kw,
    )


_OK_ROUTES = [
    ("tenant_access_token", _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})),
    ("/docx/v1/documents/blocks/convert",
     _Resp({"code": 0, "data": {"blocks": [{"block_id": "b1"}, {"block_id": "b2"}],
                                "first_level_block_ids": ["b1"]}})),
    ("/descendant", _Resp({"code": 0, "data": {"document_revision_id": 7}})),
    ("/docx/v1/documents", _Resp({"code": 0, "data": {"document": {"document_id": "doxABC"}}})),
]


def test_create_from_markdown_happy_path():
    http = _HTTP(_OK_ROUTES)
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="fld_test",
                              http=http)
    res = client.create_document_from_markdown("标题", "# H1\n\n正文")
    assert res["document_id"] == "doxABC"
    assert res["url"] == "https://r4i0myjr3j.feishu.cn/docx/doxABC"
    assert res["blocks"] == 2
    assert res["revision_id"] == 7
    # 请求体断言
    convert_call = next(c for c in http.calls if "convert" in c["url"])
    assert convert_call["json"]["content_type"] == "markdown"
    desc = next(c for c in http.calls if "descendant" in c["url"])
    assert desc["json"]["children_id"] == ["b1"]
    assert desc["json"]["descendants"] == [{"block_id": "b1"}, {"block_id": "b2"}]
    assert desc["json"]["index"] == -1


def test_create_document_passes_folder_token():
    http = _HTTP(_OK_ROUTES)
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="fld_default", http=http)
    client.create_document("t", folder_token="fld_override")
    create = next(c for c in http.calls if c["url"].endswith("/docx/v1/documents"))
    assert create["json"] == {"title": "t", "folder_token": "fld_override"}


def test_scope_error_has_hint():
    routes = [
        ("tenant_access_token", _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})),
        ("/docx/v1/documents", _Resp({"code": 99991672, "msg": "Access denied"})),
    ]
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="fld_test", http=_HTTP(routes))
    with pytest.raises(FeishuAPIError) as e:
        client.create_document("t")
    assert e.value.code == 99991672
    assert "权限" in str(e.value)


def test_folder_permission_error_hint():
    routes = [
        ("tenant_access_token", _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})),
        ("/docx/v1/documents", _Resp({"code": 1770040, "msg": "no folder permission"})),
    ]
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="fld_test", http=_HTTP(routes))
    with pytest.raises(FeishuAPIError) as e:
        client.create_document("t")
    assert "文件夹权限" in str(e.value)


def test_missing_folder_token_raises():
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="", http=_HTTP([]))
    with pytest.raises(FeishuAPIError):
        client.create_document("t")


def test_dry_run_no_network():
    http = _HTTP([])
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="fld_test",
                              http=http, dry_run=True)
    res = client.create_document_from_markdown("标题", "# H1")
    assert res["dry_run"] is True
    assert http.calls == []


def test_to_markdown_html():
    md = to_markdown("<h1>标题</h1><p>正文</p>", source="html")
    assert "标题" in md and "正文" in md


def test_to_markdown_passthrough():
    assert to_markdown("# H1", source="markdown") == "# H1"
    with pytest.raises(ValueError):
        to_markdown("x", source="xml")


def test_convert_strips_readonly_table_fields():
    routes = [
        ("tenant_access_token", _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})),
        ("/docx/v1/documents/blocks/convert", _Resp({"code": 0, "data": {
            "blocks": [
                {"block_id": "t1", "block_type": 31, "parent_id": "",
                 "table": {"cells": ["c1"], "property": {
                     "row_size": 1, "column_size": 1,
                     "merge_info": [{"col_span": 1, "row_span": 1}]}}},
            ],
            "first_level_block_ids": ["t1"],
        }})),
    ]
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="f", http=_HTTP(routes))
    conv = client.convert_to_blocks("| A |", "markdown")
    block = conv["blocks"][0]
    assert "parent_id" not in block
    assert "merge_info" not in block["table"]["property"]
    assert block["table"]["cells"] == ["c1"]
    assert block["table"]["property"]["row_size"] == 1


def test_upload_media_and_insert_image(tmp_path):
    png = tmp_path / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n0000")
    routes = [
        ("tenant_access_token", _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})),
        ("/children", _Resp({"code": 0, "data": {"children": [{"block_id": "imgblk1"}]}})),
        ("/drive/v1/medias/upload_all", _Resp({"code": 0, "data": {"file_token": "boximg1"}})),
        ("/blocks/imgblk1", _Resp({"code": 0, "data": {"block_id": "imgblk1"}})),
    ]
    http = _HTTP(routes)
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="f", http=http)
    res = client.insert_image("doxABC", png)
    assert res["file_token"] == "boximg1"

    up = next(c for c in http.calls if "upload_all" in c["url"])
    assert up["method"] == "POST"
    assert up["data"]["parent_type"] == "docx_image"
    assert up["data"]["parent_node"] == "imgblk1"
    assert '"drive_route_token": "doxABC"' in up["data"]["extra"]
    assert up["files"]["file"][0] == "chart.png"

    child = next(c for c in http.calls if "/children" in c["url"])
    assert child["json"]["children"][0] == {"block_type": 27, "image": {}}
    assert child["json"]["index"] == -1
    patch = next(c for c in http.calls if "/blocks/imgblk1" in c["url"])
    assert patch["method"] == "PATCH"
    assert patch["json"] == {"replace_image": {"token": "boximg1"}}


def test_insert_image_dry_run_no_network(tmp_path):
    png = tmp_path / "chart.png"
    png.write_bytes(b"x")
    http = _HTTP([])
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="f",
                              http=http, dry_run=True)
    res = client.insert_image("doxABC", png)
    assert res["dry_run"] is True
    assert http.calls == []


def test_upload_media_missing_file_raises(tmp_path):
    http = _HTTP([("tenant_access_token",
                   _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200}))])
    client = FeishuDocxClient(app_id="cli_test", app_secret="s", folder_token="f", http=http)
    with pytest.raises(FeishuAPIError):
        client.upload_media(tmp_path / "nope.png", parent_node="doxABC")
