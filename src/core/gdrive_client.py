# -*- coding: utf-8 -*-
"""Google Drive REST API v3 연동 및 OAuth 토큰 관리 모듈 (외부 SDK 불필요, 표준 urllib 사용)."""

import io
import json
import logging
import os
import time
from typing import Optional
import urllib.parse
import urllib.request
import urllib.error

from core.bot_logger import get_logger

logger = get_logger("gdrive_client")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DEFAULT_BACKUP_FOLDER = "supabot-backups"

DEFAULT_META_TIMEOUT = 15.0
DEFAULT_TRANSFER_TIMEOUT = 300.0


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """OAuth Authorization code를 access_token 및 refresh_token으로 교환합니다."""
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_META_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", errors="ignore")
        logger.error("Failed to exchange code for tokens: %s", err_body)
        raise ValueError("Google OAuth 토큰 교환에 실패했습니다.") from error


def fetch_google_user_email(access_token: str) -> str:
    """Access token을 사용하여 연동된 Google 사용자 이메일을 조회합니다."""
    req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_META_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("email", "")
    except Exception as error:
        logger.warning("Failed to fetch Google user email: %s", error)
        return ""


def get_google_auth_url(client_id: str, redirect_uri: str, scope: Optional[str] = None) -> str:
    """Google OAuth2 인증 URL을 생성합니다."""
    if not scope:
        scope = "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh token을 사용하여 새 access_token을 발급받습니다."""
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_META_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", errors="ignore")
        logger.error("Failed to refresh access token: %s", err_body)
        raise ValueError("Google access_token 갱신에 실패했습니다.") from error


def ensure_backup_folder_exists(access_token: str, folder_name: str = DEFAULT_BACKUP_FOLDER) -> str:
    """Google Drive 내 백업 전용 폴더 ID를 조회하거나 생성합니다."""
    query = f"mimeType='{FOLDER_MIME_TYPE}' and name='{folder_name}' and trashed=false"
    url = f"{DRIVE_FILES_URL}?q={urllib.parse.quote(query)}"

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET"
    )

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_META_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            files = data.get("files", [])
            if files:
                return files[0]["id"]
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", errors="ignore")
        logger.error("Failed to search folder in Google Drive: %s - %s", error, err_body)
        if error.code == 401:
            raise ValueError("Google Drive 연동 토큰이 만료되었습니다.") from error
        if error.code == 403:
            raise ValueError("Google Drive 접근 권한이 거부되었습니다 (403).") from error
        raise ValueError(f"Google Drive 폴더 검색 실패 ({error.code}).") from error

    # 폴더가 없으면 새로 생성
    metadata = {
        "name": folder_name,
        "mimeType": FOLDER_MIME_TYPE,
    }
    create_req = urllib.request.Request(
        DRIVE_FILES_URL,
        data=json.dumps(metadata).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(create_req, timeout=DEFAULT_META_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["id"]
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", errors="ignore")
        logger.error("Failed to create folder in Google Drive: %s - %s", error, err_body)
        if error.code == 401:
            raise ValueError("Google Drive 연동 토큰이 만료되었습니다.") from error
        raise ValueError(f"Google Drive 폴더 생성 실패 ({error.code}).") from error


def _request_with_backoff(req_factory, max_retries: int = 3, timeout: float = DEFAULT_TRANSFER_TIMEOUT):
    """429 또는 5xx 일시적 오류 시 지수 백오프(1s, 2s, 4s)로 재시도합니다."""
    for attempt in range(max_retries):
        try:
            req = req_factory()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                sleep_sec = 2 ** attempt
                logger.warning(
                    "Google Drive API returned %d, retrying in %ds (attempt %d/%d)...",
                    error.code, sleep_sec, attempt + 1, max_retries
                )
                time.sleep(sleep_sec)
                continue
            raise


def _upload_resumable(
    access_token: str,
    file_path: str,
    filename: str,
    mime_type: str,
    folder_id: str,
    existing_file_id: Optional[str] = None,
) -> dict:
    """5MB 이상의 대용량 파일을 Google Drive Resumable Upload 프로토콜로 분할 스트리밍 전송합니다."""
    file_size = os.path.getsize(file_path)
    metadata = {"name": filename}
    if not existing_file_id:
        metadata["parents"] = [folder_id]

    meta_bytes = json.dumps(metadata).encode("utf-8")
    if existing_file_id:
        init_url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_file_id}?uploadType=resumable"
        init_method = "PATCH"
    else:
        init_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
        init_method = "POST"

    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": mime_type,
        "X-Upload-Content-Length": str(file_size),
    }

    def _create_init_req():
        return urllib.request.Request(init_url, data=meta_bytes, headers=init_headers, method=init_method)

    status, headers, _ = _request_with_backoff(_create_init_req, max_retries=3, timeout=DEFAULT_META_TIMEOUT)
    session_url = headers.get("location") or headers.get("Location")
    if not session_url:
        raise ValueError("Google Drive Resumable Upload 세션 생성에 실패했습니다 (Location 헤더 없음).")

    chunk_size = 1024 * 1024  # 1MB 단위
    with open(file_path, "rb") as f:
        bytes_sent = 0
        while bytes_sent < file_size:
            chunk = f.read(chunk_size)
            chunk_len = len(chunk)
            range_header = f"bytes {bytes_sent}-{bytes_sent + chunk_len - 1}/{file_size}"
            bytes_sent += chunk_len

            def _create_chunk_req(current_chunk=chunk, current_range=range_header):
                return urllib.request.Request(
                    session_url,
                    data=current_chunk,
                    headers={
                        "Content-Length": str(len(current_chunk)),
                        "Content-Range": current_range,
                    },
                    method="PUT",
                )

            status, _, body = _request_with_backoff(_create_chunk_req, max_retries=3, timeout=DEFAULT_TRANSFER_TIMEOUT)
            if status in (200, 201):
                return json.loads(body.decode("utf-8"))

    raise ValueError("Google Drive Resumable Upload가 비정상 종료되었습니다.")


def upload_file_to_gdrive(
    access_token: str,
    file_path: str,
    filename: str,
    mime_type: str = "application/zip",
    existing_file_id: Optional[str] = None,
    folder_name: str = DEFAULT_BACKUP_FOLDER,
) -> dict:
    """파일을 Google Drive 백업 폴더로 업로드합니다 (5MB 이상 Resumable, 미만 Multipart)."""
    folder_id = ensure_backup_folder_exists(access_token, folder_name=folder_name)
    file_size = os.path.getsize(file_path)

    if file_size >= 5 * 1024 * 1024:
        try:
            return _upload_resumable(
                access_token=access_token,
                file_path=file_path,
                filename=filename,
                mime_type=mime_type,
                folder_id=folder_id,
                existing_file_id=existing_file_id,
            )
        except Exception as e:
            logger.warning("Resumable upload failed (%s), falling back to multipart upload", e)

    metadata = {"name": filename}
    if not existing_file_id:
        metadata["parents"] = [folder_id]

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    boundary = "====================SupabotBackupBoundary=="
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b"Content-Type: application/json; charset=UTF-8\r\n\r\n")
    body.write(json.dumps(metadata).encode("utf-8"))
    body.write(b"\r\n")
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.write(file_bytes)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode("utf-8"))

    body_content = body.getvalue()

    if existing_file_id:
        url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_file_id}?uploadType=multipart"
        method = "PATCH"
    else:
        url = DRIVE_UPLOAD_URL
        method = "POST"

    def _create_multipart_req():
        return urllib.request.Request(
            url,
            data=body_content,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
                "Content-Length": str(len(body_content)),
            },
            method=method,
        )

    try:
        _, _, resp_body = _request_with_backoff(_create_multipart_req, max_retries=3, timeout=DEFAULT_TRANSFER_TIMEOUT)
        return json.loads(resp_body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", errors="ignore")
        logger.error("Failed to upload file to Google Drive: %s", err_body)
        raise ValueError("Google Drive 파일 업로드에 실패했습니다.") from error


def list_gdrive_backups(access_token: str, folder_name: str = DEFAULT_BACKUP_FOLDER) -> list[dict]:
    """Google Drive 백업 폴더 내 파일 목록을 최신순으로 반환합니다."""
    folder_id = ensure_backup_folder_exists(access_token, folder_name=folder_name)
    result = []
    page_token = None

    while True:
        query = f"'{folder_id}' in parents and trashed=false"
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,size,createdTime,modifiedTime)",
            "orderBy": "createdTime desc",
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token

        url = f"{DRIVE_FILES_URL}?{urllib.parse.urlencode(params)}"

        def _create_list_req():
            return urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                method="GET",
            )

        try:
            _, _, body = _request_with_backoff(_create_list_req, max_retries=3, timeout=DEFAULT_META_TIMEOUT)
            data = json.loads(body.decode("utf-8"))
            files = data.get("files", [])
            for f in files:
                result.append({
                    "id": f["id"],
                    "filename": f["name"],
                    "sizeBytes": int(f.get("size", 0)),
                    "createdAt": f.get("createdTime", f.get("modifiedTime", "")),
                })
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        except Exception as error:
            logger.error("Failed to list files from Google Drive: %s", error)
            break

    return result


def download_file_from_gdrive(access_token: str, file_id: str) -> bytes:
    """Google Drive에서 지정한 file_id 파일 바이너리를 다운로드합니다."""
    url = f"{DRIVE_FILES_URL}/{file_id}?alt=media"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TRANSFER_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as error:
        logger.error("Failed to download file from Google Drive: %s", error)
        raise ValueError("Google Drive 파일 다운로드에 실패했습니다.") from error


def delete_file_from_gdrive(access_token: str, file_id: str) -> None:
    """Google Drive에서 지정한 file_id 파일을 삭제합니다."""
    url = f"{DRIVE_FILES_URL}/{file_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="DELETE"
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_META_TIMEOUT):
            pass
    except urllib.error.HTTPError as error:
        logger.warning("Failed to delete file from Google Drive: %s", error)
