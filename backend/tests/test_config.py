"""数据库连接串必须原样保留用户名和密码中的特殊字符。"""
import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings


@pytest.mark.parametrize("password", ["p@ss:/?#%+word", "含中文的密码@123", ""])
def test_database_url_credentials_round_trip(password):
    settings = Settings.model_construct(MYSQL_USER="user@local", MYSQL_PASSWORD=password)
    url = make_url(settings.database_url)
    assert url.username == "user@local"
    assert url.password == password
    assert url.host == settings.MYSQL_HOST
    assert url.database == settings.MYSQL_DB
