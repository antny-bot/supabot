# -*- coding: utf-8 -*-
import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from core import gdrive_client


def test_refresh_access_token_success():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "access_token": "new_access_token_123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = gdrive_client.refresh_access_token("client_id", "client_secret", "refresh_tok")
        assert result["access_token"] == "new_access_token_123"
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "POST"
        assert req.full_url == gdrive_client.GOOGLE_TOKEN_URL


def test_refresh_access_token_failure():
    mock_err = urllib.error.HTTPError(
        url=gdrive_client.GOOGLE_TOKEN_URL,
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(b'{"error": "invalid_grant"}'),
    )
    with patch("urllib.request.urlopen", side_effect=mock_err):
        with pytest.raises(ValueError, match="Google access_token 갱신에 실패했습니다"):
            gdrive_client.refresh_access_token("cid", "sec", "bad_token")


def test_ensure_backup_folder_exists_found():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "files": [{"id": "folder_123", "name": "supabot-backups"}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        folder_id = gdrive_client.ensure_backup_folder_exists("test_tok", "supabot-backups")
        assert folder_id == "folder_123"


def test_ensure_backup_folder_exists_create_new():
    # 1st call (search): empty, 2nd call (create): returns new folder id
    mock_resp_search = MagicMock()
    mock_resp_search.read.return_value = json.dumps({"files": []}).encode("utf-8")
    mock_resp_search.__enter__.return_value = mock_resp_search

    mock_resp_create = MagicMock()
    mock_resp_create.read.return_value = json.dumps({"id": "created_folder_456"}).encode("utf-8")
    mock_resp_create.__enter__.return_value = mock_resp_create

    with patch("urllib.request.urlopen", side_effect=[mock_resp_search, mock_resp_create]):
        folder_id = gdrive_client.ensure_backup_folder_exists("test_tok", "supabot-backups")
        assert folder_id == "created_folder_456"


def test_upload_file_multipart(tmp_path):
    test_file = tmp_path / "test.zip"
    test_file.write_bytes(b"PK\x03\x04test zip content")

    mock_folder_resp = MagicMock()
    mock_folder_resp.read.return_value = json.dumps({"files": [{"id": "folder_999"}]}).encode("utf-8")
    mock_folder_resp.__enter__.return_value = mock_folder_resp

    mock_upload_resp = MagicMock()
    mock_upload_resp.status = 200
    mock_upload_resp.headers = {}
    mock_upload_resp.read.return_value = json.dumps({"id": "file_888", "name": "test.zip"}).encode("utf-8")
    mock_upload_resp.__enter__.return_value = mock_upload_resp

    with patch("urllib.request.urlopen", side_effect=[mock_folder_resp, mock_upload_resp]):
        res = gdrive_client.upload_file_to_gdrive("test_tok", str(test_file), "test.zip")
        assert res["id"] == "file_888"


def test_list_gdrive_backups():
    mock_folder_resp = MagicMock()
    mock_folder_resp.read.return_value = json.dumps({"files": [{"id": "folder_999"}]}).encode("utf-8")
    mock_folder_resp.__enter__.return_value = mock_folder_resp

    mock_list_resp = MagicMock()
    mock_list_resp.status = 200
    mock_list_resp.headers = {}
    mock_list_resp.read.return_value = json.dumps({
        "files": [
            {"id": "f1", "name": "backup-20261107.zip", "size": "1048576", "createdTime": "2026-11-07T00:00:00Z"},
            {"id": "f2", "name": "backup-20261106.zip", "size": "1048576", "createdTime": "2026-11-06T00:00:00Z"},
        ]
    }).encode("utf-8")
    mock_list_resp.__enter__.return_value = mock_list_resp

    with patch("urllib.request.urlopen", side_effect=[mock_folder_resp, mock_list_resp]):
        backups = gdrive_client.list_gdrive_backups("test_tok", "supabot-backups")
        assert len(backups) == 2
        assert backups[0]["id"] == "f1"
        assert backups[0]["sizeBytes"] == 1048576


def test_delete_file_from_gdrive():
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.headers = {}
    mock_resp.read.return_value = b""
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        gdrive_client.delete_file_from_gdrive("test_tok", "file_to_del")
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "DELETE"
        assert "file_to_del" in req.full_url
