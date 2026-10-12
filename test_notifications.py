from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import PushSubscription, PushLog, User
from config import settings
from push_service import (
    get_vapid_public_key,
    register_subscription,
    unregister_subscription,
    broadcast_notification,
    check_and_send_daily_news_digest
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_cookie(client):
    res = client.post(
        "/login",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD
        },
        follow_redirects=False
    )
    cookie = res.cookies.get(settings.SESSION_COOKIE_NAME)
    return {settings.SESSION_COOKIE_NAME: cookie}


def test_service_worker_route(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "").lower()
    assert "self.addEventListener" in response.text
    assert "Service-Worker-Allowed" in response.headers


def test_vapid_public_key_route(client):
    response = client.get("/api/push/vapid-public-key")
    assert response.status_code == 200
    data = response.json()
    assert "public_key" in data
    assert len(data["public_key"]) >= 80
    assert data["public_key"].startswith("B")


def test_subscribe_and_unsubscribe_lifecycle(client):
    db = SessionLocal()
    # Limpa assinaturas de teste
    db.query(PushSubscription).filter(PushSubscription.endpoint.like("https://push.test/%")).delete()
    db.commit()
    db.close()

    payload = {
        "endpoint": "https://push.test/sub-12345",
        "p256dh": "BDUs5Y7v_tZvenSJQEajxQFaIBR9HIVtmYyzLzVoHs2NcS4ZiVU_eqI9acM35KugL122my-BGeqld8MW2L_3N4E",
        "auth": "tBHItJI5svbpez7KI4CCXg",
        "user_agent": "Mozilla/5.0 Chrome Test"
    }

    # 1. Registro
    sub_res = client.post("/api/push/subscribe", json=payload)
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "ok"

    # Verifica persistencia no banco
    db = SessionLocal()
    sub_db = db.query(PushSubscription).filter(PushSubscription.endpoint == payload["endpoint"]).first()
    assert sub_db is not None
    assert sub_db.auth == payload["auth"]
    db.close()

    # 2. Re-registro (atualizacao idempotente)
    payload["auth"] = "novo-auth-token"
    sub_res2 = client.post("/api/push/subscribe", json=payload)
    assert sub_res2.status_code == 200

    db = SessionLocal()
    sub_db_updated = db.query(PushSubscription).filter(PushSubscription.endpoint == payload["endpoint"]).first()
    assert sub_db_updated.auth == "novo-auth-token"
    db.close()

    # 3. Cancelamento (unsubscribe)
    unsub_res = client.post("/api/push/unsubscribe", json={"endpoint": payload["endpoint"]})
    assert unsub_res.status_code == 200
    assert unsub_res.json()["removed"] is True

    db = SessionLocal()
    sub_db_removed = db.query(PushSubscription).filter(PushSubscription.endpoint == payload["endpoint"]).first()
    assert sub_db_removed is None
    db.close()


def test_broadcast_with_stale_cleanup():
    db = SessionLocal()
    # Cria duas assinaturas de teste
    sub_alive = register_subscription(
        db=db,
        endpoint="https://push.test/alive-client",
        p256dh="alive_p256dh_key",
        auth="alive_auth"
    )
    sub_dead = register_subscription(
        db=db,
        endpoint="https://push.test/dead-client",
        p256dh="dead_p256dh_key",
        auth="dead_auth"
    )
    db.close()

    # Simula envio onde o endpoint morto retorna 410 Gone
    def mock_send(sub, payload):
        if "dead-client" in sub.endpoint:
            return False, "unregistered"
        return True, None

    with patch("push_service.send_single_push", side_effect=mock_send):
        result = broadcast_notification(
            title="Teste Automatizado",
            body="Mensagem de teste de broadcast.",
            target_url="/",
            notification_type="manual"
        )

    assert result["success"] >= 1
    assert result["removed_stale"] >= 1

    # Verifica que o endpoint morto foi purgado do banco
    db = SessionLocal()
    check_dead = db.query(PushSubscription).filter(PushSubscription.endpoint == "https://push.test/dead-client").first()
    assert check_dead is None

    # E o log foi gravado
    last_log = db.query(PushLog).order_by(PushLog.sent_at.desc()).first()
    assert last_log is not None
    assert last_log.title == "Teste Automatizado"

    # Limpeza
    db.query(PushSubscription).filter(PushSubscription.endpoint == "https://push.test/alive-client").delete()
    db.commit()
    db.close()


def test_admin_push_dashboard_and_actions(client, admin_cookie):
    # Acessa aba de push no admin
    res = client.get("/admin?tab=push", cookies=admin_cookie)
    assert res.status_code == 200
    assert "STATUS DO PROTOCOLO WEB PUSH NATIVO" in res.text
    assert "DISPARO MANUAL OU TESTE" in res.text
    assert "RESUMO DIARIO DO RADAR" in res.text

    # Disparo manual via formulario admin
    broadcast_res = client.post(
        "/admin/push/broadcast",
        data={
            "title": "Aviso da Administracao",
            "body": "Texto de teste enviado pelo admin.",
            "target_url": "/"
        },
        cookies=admin_cookie,
        follow_redirects=False
    )
    assert broadcast_res.status_code in (302, 303)
    assert "/admin?tab=push" in broadcast_res.headers["location"]

    # Forcar resumo do radar
    digest_res = client.post(
        "/admin/push/digest-now",
        cookies=admin_cookie,
        follow_redirects=False
    )
    assert digest_res.status_code in (302, 303)
    assert "/admin?tab=push" in digest_res.headers["location"]


def test_daily_news_digest_throttle():
    db = SessionLocal()
    # Limpa logs de teste
    db.query(PushLog).filter(PushLog.notification_type == "news_digest").delete()
    db.commit()
    db.close()

    with patch("push_service.send_single_push", return_value=(True, None)):
        # Primeiro envio deve disparar e gravar log
        sent_first = check_and_send_daily_news_digest()
        assert sent_first is True

        # Segundo envio imediato deve ser travado pelo throttle de 24h
        sent_second = check_and_send_daily_news_digest()
        assert sent_second is False

    # Limpeza
    db = SessionLocal()
    db.query(PushLog).filter(PushLog.notification_type == "news_digest").delete()
    db.commit()
    db.close()
