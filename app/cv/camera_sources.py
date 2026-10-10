"""Normalize camera sources and keep credentials out of public status."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


NETWORK_SCHEMES = {'rtsp', 'rtsps', 'http', 'https'}


def normalize_source(source: str | int) -> str | int:
    value = str(source).strip()
    if not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError('Nguồn camera không được trống hoặc chứa ký tự điều khiển.')
    if value.lstrip('-').isascii() and value.lstrip('-').isdigit():
        index = int(value)
        if index < 0 or index > 255:
            raise ValueError('Chỉ số webcam phải từ 0 đến 255.')
        return index
    return value


def is_network_source(source: str | int) -> bool:
    return isinstance(source, str) and source.split(':', 1)[0].lower() in NETWORK_SCHEMES


def validate_source(source: str | int) -> str | int:
    value = normalize_source(source)
    if isinstance(value, int):
        return value
    if is_network_source(value):
        try:
            url = urlsplit(value)
            if not url.hostname or (url.port is not None and not 1 <= url.port <= 65535):
                raise ValueError
        except ValueError:
            raise ValueError('URL camera không hợp lệ.') from None
        return value
    if '://' in value:
        raise ValueError('Chỉ hỗ trợ RTSP, RTSPS, HTTP, HTTPS hoặc video trên máy chủ.')
    path = Path(value).expanduser()
    if path.suffix.lower() not in {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v'} or not path.is_file():
        raise ValueError('Không tìm thấy file video hợp lệ trên máy chủ.')
    return str(path.resolve())


def display_source(source: str | int | None) -> str:
    if source is None:
        return ''
    if not is_network_source(source):
        return str(source)
    try:
        url = urlsplit(source)
        # Drop userinfo, query and fragment: all may contain credentials.
        return urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], url.path, '', ''))
    except ValueError:
        return '(URL camera)'
